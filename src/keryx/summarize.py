"""Shrink a reply to one or two spoken sentences with a local Ollama model."""

from __future__ import annotations

import http.client
import json
import re
import urllib.request
from collections.abc import Callable
from typing import Protocol

from keryx.config import Config, keep_alive_seconds
from keryx.text import clean_for_speech, first_sentences

SYSTEM_PROMPT = (
    "You rewrite a coding assistant's message as one or two short sentences that the "
    "assistant will say out loud to the developer. Lead with the main outcome or decision. "
    "Keep who did what: 'I' is the assistant who wrote the message, 'you' is the developer; "
    "never attribute the developer's words or actions to 'I'. Keep a question a question: "
    "never turn an offer or question into a done action or pending work. Claim something is "
    "done only where the message marks it done; dropped or removed items are not done work. "
    "When the message drafts text for the developer to send, say 'here is a draft for you "
    "to send'. Keep pending work pending: if something is running, waiting, or planned, say so. "
    "Mention a request only if the message asks for something; never add a request. Never "
    "reply to the message, comment on it, or ask a question it did not ask. Use only facts "
    "from this message. No markdown, lists, code, file paths or ID numbers. At most 35 words. "
    "Output only the sentences."
)

FAITHFULNESS_SYSTEM_PROMPT = (
    "You are a strict faithfulness judge for a spoken coding assistant summarizer. "
    "Check if the spoken summary is completely faithful to the source message. "
    "Flag unfaithful if: an offer/question is turned into a done action or pending work; "
    "a removed or dropped item is described as updated or done; a draft for the developer "
    "is claimed as the assistant's own act; who did what is flipped (e.g. developer's words "
    "attributed to 'I'); or pending work is described as done. "
    "Reply with only 'FAITHFUL' or 'UNFAITHFUL: <reason>'."
)

# Made-up examples showing the shape of the task; deliberately unlike real replies so
# their wording has nothing to leak into.
EXAMPLES = (
    (
        "Status: Renamed the ocean-temperature column in the weather loader and updated "
        "both notebooks that read it. All 118 tests pass and the branch is pushed. One "
        "question: should the old column name stay as an alias for a release, or go now?",
        "I renamed the ocean temperature column and updated both notebooks; tests pass and "
        "it's pushed. Should the old name stay as an alias for a release, or go now?",
    ),
    (
        "The legacy parser is off the list. The bakery-orders export is done, but the staging "
        "deploy is still running. Here is a draft note for you to send: 'Export is updated.' "
        "Want me to check the logs next?",
        "The legacy parser is off the list and export is done, but staging is still running. "
        "Here is a draft note for you to send. Would you like me to check the logs next?",
    ),
)

# Ollama turns seconds into a Go duration, which overflows to negative (unload now) past
# about 9.2e9 s; anything that long means "keep it loaded", which is -1.
MAX_KEEP_ALIVE_SECONDS = 9e9


def ollama_keep_alive(value: str) -> float:
    """`keep_alive` as the seconds Ollama is sent: a number always, so Ollama never parses a
    duration string; -1 (keep loaded) for any negative or overlong value."""
    seconds = keep_alive_seconds(value)
    if seconds is None:
        seconds = keep_alive_seconds(Config().keep_alive) or 0.0
    if seconds < 0 or seconds > MAX_KEEP_ALIVE_SECONDS:
        return -1
    return int(seconds) if seconds == int(seconds) else seconds


# Ollama aborts a load when its client hangs up, so this must outlast a cold load:
# 4-14 s with the model file in the page cache, 44 s read from disk (2026-10-02).
LOAD_TIMEOUT = 120.0
GENERATE_TIMEOUT = 30.0

# Replies this short are spoken as-is; anything longer goes through the model.
DIRECT_MAX_CHARS = 200
SPOKEN_MAX_CHARS = 320

# The densest measured reply at MAX_INPUT_CHARS was a 3924-token prompt; with NUM_PREDICT
# it fits NUM_CTX (2026-10-21).
NUM_CTX = 4096
NUM_PREDICT = 96
MAX_INPUT_CHARS = 5600
ELISION = " … "


class Generator(Protocol):
    def generate(self, prompt: str, system: str) -> str: ...


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout: float = GENERATE_TIMEOUT,
        load_timeout: float = LOAD_TIMEOUT,
        keep_alive: str = Config().keep_alive,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.load_timeout = load_timeout
        self.keep_alive = keep_alive

    def generate(self, prompt: str, system: str) -> str:
        # Load first under the long timeout; `timeout` then bounds generation alone.
        self.warm()
        messages = [{"role": "system", "content": system}]
        for message, spoken in EXAMPLES:
            messages.append({"role": "user", "content": _framed(message)})
            messages.append({"role": "assistant", "content": spoken})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": ollama_keep_alive(self.keep_alive),
            "options": {"temperature": 0.2, "num_predict": NUM_PREDICT, "num_ctx": NUM_CTX},
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)["message"]["content"]

    def warm(self) -> None:
        """Load the model now (an empty generate) so the next reply skips the cold load."""
        self._load(ollama_keep_alive(self.keep_alive))

    def unload(self) -> None:
        """Hand the model's VRAM back now instead of when `keep_alive` runs out."""
        self._load(0)

    def _load(self, keep_alive: float) -> None:
        body = {
            "model": self.model,
            "keep_alive": keep_alive,
            "options": {"num_ctx": NUM_CTX},
        }
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.load_timeout) as resp:
            resp.read()


def _framed(message: str) -> str:
    return f"Message to rewrite:\n<message>\n{message}\n</message>"


def model_input(cleaned: str) -> str:
    """`cleaned` whole when it fits MAX_INPUT_CHARS, else its opening and its close, where a
    question to the developer usually sits."""
    if len(cleaned) <= MAX_INPUT_CHARS:
        return cleaned
    half = (MAX_INPUT_CHARS - len(ELISION)) // 2
    head = cleaned[:half].rsplit(" ", 1)[0]
    tail = cleaned[-half:].split(" ", 1)[-1]
    return f"{head}{ELISION}{tail}"


def check_faithfulness(summary: str, source: str) -> tuple[bool, str | None]:
    """Check whether `summary` is faithful to `source` text according to keryx rubric.

    Returns (True, None) if faithful, or (False, reason) if unfaithful.
    """
    s_sum = summary.strip()
    s_src = source.strip()

    # 1. Question / Offer converted to done or pending action
    if "?" not in s_sum:
        offer_patterns = [
            r"\b(?:want\s+me\s+to|would\s+you\s+like\s+me\s+to|should\s+i|shall\s+i|can\s+i)"
            r"\s+([^?.!\n]+)\?",
        ]
        stopwords = {
            "it",
            "the",
            "a",
            "an",
            "this",
            "that",
            "to",
            "for",
            "with",
            "and",
            "or",
            "some",
        }
        for pattern in offer_patterns:
            m = re.search(pattern, s_src, re.IGNORECASE)
            if m:
                action_phrase = m.group(1).strip().lower()
                keywords = [
                    w for w in re.findall(r"\b[a-z]{3,}\b", action_phrase) if w not in stopwords
                ]
                action_asserted = re.search(
                    r"\b(?:is\s+pending|pending|i\s+added|i\s+updated|i\s+created|i\s+fixed|i\s+did)\b",
                    s_sum,
                    re.IGNORECASE,
                )
                done_in_src = re.search(
                    r"\b(?:done|finished|completed|already\s+added)\b", s_src, re.IGNORECASE
                )
                kw_in_sum = any(kw in s_sum.lower() for kw in keywords)
                if keywords and action_asserted and kw_in_sum and not done_in_src:
                    return False, "question_as_action"

    # 2. Removed / Dropped items claimed as updated or done
    drop_patterns = [
        r"(\b[A-Za-z0-9_-]+\b)\s*(?:✅|✔)?\s*(?:is\s+)?(?:off\s+the\s+list|dropped|removed|scrapped|leave\s+it)",
        r"(?:off\s+the\s+list|dropped|removed|scrapped)\s*[:;,-]?\s*(\b[A-Za-z0-9_-]+\b)",
    ]
    for pattern in drop_patterns:
        for match in re.finditer(pattern, s_src, re.IGNORECASE):
            item = match.group(1).strip()
            if len(item) >= 2 and item.lower() not in {"it", "this", "that"}:
                pattern_claim = (
                    rf"\b(?:updated|modified|revised|fixed|completed|worked\s+on)"
                    rf"\b[^.!?\n]*\b{re.escape(item)}\b"
                )
                pattern_claim_rev = (
                    rf"\b{re.escape(item)}\b[^.!?\n]*"
                    r"\b(?:updated|modified|revised|fixed|completed|done)\b"
                )
                if re.search(pattern_claim, s_sum, re.IGNORECASE) or re.search(
                    pattern_claim_rev, s_sum, re.IGNORECASE
                ):
                    return False, "removed_item_as_done"

    # 3. Draft for developer claimed as assistant's act
    has_draft = re.search(
        r"\b(?:draft\s+(?:team\s+)?(?:message|email|note|announcement)|draft\s+for\s+(?:you|aj)\s+to\s+send)\b",
        s_src,
        re.IGNORECASE,
    )
    claimed_sent = re.search(
        r"\bI(?:'ve|\s+have)?\s+(?:sent|posted|emailed|published|created\s+a\s+pinned\s+list)\b",
        s_sum,
        re.IGNORECASE,
    )
    if has_draft and claimed_sent:
        return False, "draft_claimed_by_assistant"

    # 4. Attribution flip (developer's words/actions claimed as assistant's)
    attr_match = re.search(
        r"\b(?:you\s+(?:noted|said|mentioned|observed|pointed\s+out|suggested)|"
        r"your\s+(?:note|idea|observation|suggestion))\b[^.!?\n]*['\"]([^'\"]+)['\"]",
        s_src,
        re.IGNORECASE,
    )
    if attr_match:
        quoted = attr_match.group(1).strip()
        quoted_words = [
            w.lower()
            for w in re.findall(r"\b[a-z]{4,}\b", quoted)
            if w.lower() not in {"that", "this", "with", "have", "from", "they", "were", "been"}
        ]
        if quoted_words:
            claim_match = re.search(
                r"\bI(?:'ve|\s+have)?\s+(?:identified|noticed|found|suggested|came\s+up\s+with)\b([^.!?\n]+)",
                s_sum,
                re.IGNORECASE,
            )
            if claim_match and any(qw in claim_match.group(1).lower() for qw in quoted_words):
                return False, "attribution_flip"

    # 5. Pending item claimed as completed
    pending_match = re.search(
        r"\b([A-Za-z0-9_-]+(?:\s+[A-Za-z0-9_-]+)?)\s+(?:is|are)\s+still\s+(?:running|pending|deploying|waiting)\b",
        s_src,
        re.IGNORECASE,
    )
    if pending_match:
        target = pending_match.group(1).strip()
        claimed_done = re.search(
            rf"\b(?:done|finished|completed|deployed|merged)\b[^.!?\n]*\b{re.escape(target)}\b",
            s_sum,
            re.IGNORECASE,
        ) or re.search(
            rf"\b{re.escape(target)}\b[^.!?\n]*\b(?:done|finished|completed|deployed|merged)\b",
            s_sum,
            re.IGNORECASE,
        )
        is_pending = re.search(r"\b(?:still\s+running|pending|waiting)\b", s_sum, re.IGNORECASE)
        if claimed_done and not is_pending:
            return False, "pending_claimed_as_done"

    return True, None


def is_faithful(summary: str, source: str) -> bool:
    """Whether `summary` faithfully captures `source` without hallucinating claims or actions."""
    return check_faithfulness(summary, source)[0]


def spoken(
    reply: str, client: Generator | None, gate: Callable[[], str | None] | None = None
) -> tuple[str, str]:
    """The words to say for `reply` and the path that made them: "direct" (short, or no
    model), "model", "trimmed: <reason>" (`gate` said memory is low) or "fallback" (the
    model failed, unfaithful, or said nothing)."""
    cleaned = clean_for_speech(reply)
    opening = first_sentences(cleaned, SPOKEN_MAX_CHARS)
    if len(cleaned) <= DIRECT_MAX_CHARS or client is None:
        return opening, "direct"
    reason = gate() if gate else None
    if reason:
        return opening, f"trimmed: {reason}"
    try:
        out = client.generate(_framed(model_input(cleaned)), SYSTEM_PROMPT)
    except (OSError, http.client.HTTPException, KeyError, ValueError, TypeError):
        return opening, "fallback"
    line = first_sentences(clean_for_speech(out).strip("\"' "), SPOKEN_MAX_CHARS)
    if not line:
        return opening, "fallback"
    if not is_faithful(line, cleaned):
        try:
            retry_prompt = (
                f"{_framed(model_input(cleaned))}\n\n"
                f"Your previous summary was unfaithful: '{line}'. "
                "Rewrite it accurately: keep who did what (I vs you), keep a question a "
                "question, do not turn offers into done or pending actions, and do not "
                "claim removed items are updated. Output only the sentences."
            )
            retry_out = client.generate(retry_prompt, SYSTEM_PROMPT)
            cleaned_retry = clean_for_speech(retry_out).strip("\"' ")
            retry_line = first_sentences(cleaned_retry, SPOKEN_MAX_CHARS)
            if retry_line and is_faithful(retry_line, cleaned):
                return retry_line, "model"
        except (OSError, http.client.HTTPException, KeyError, ValueError, TypeError):
            pass
        return opening, "fallback"
    return line, "model"


def spoken_line(
    reply: str, client: Generator | None, gate: Callable[[], str | None] | None = None
) -> str:
    """The words to say for `reply`: as-is if short, else the model's gist, else its opening."""
    return spoken(reply, client, gate)[0]
