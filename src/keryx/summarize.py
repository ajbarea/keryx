"""Shrink a reply to one or two spoken sentences with a local Ollama model."""

from __future__ import annotations

import http.client
import json
import urllib.request
from collections.abc import Callable
from typing import Protocol

from keryx.config import Config, keep_alive_seconds
from keryx.text import clean_for_speech, first_sentences

SYSTEM_PROMPT = (
    "You rewrite a coding assistant's message as one or two short sentences that the "
    "assistant will say out loud to the developer. Keep the assistant's point of view: "
    "'I' is the assistant who wrote the message, 'you' is the developer. Say the main "
    "outcome. Keep pending work pending: if something is still running, waiting for "
    "approval, or only planned, say so; never call it done. Mention a request only if the "
    "message itself asks the developer for something, and keep a question a question; "
    "never add a request. Never reply to the message, comment on it, or ask a question it "
    "did not ask. Use only facts from this message. No markdown, lists, code, file paths or "
    "ID numbers. At most 35 words. Output only the sentences."
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
        "The bakery-orders export is done: the CSV now includes delivery windows, the old "
        "XML route is deleted, and the docs page lists the new fields. The staging deploy "
        "is still running; I'll check it when it finishes.",
        "The bakery orders export now includes delivery windows and the old XML route is "
        "gone. The staging deploy is still running, and I'll check it when it finishes.",
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


def spoken(
    reply: str, client: Generator | None, gate: Callable[[], str | None] | None = None
) -> tuple[str, str]:
    """The words to say for `reply` and the path that made them: "direct" (short, or no
    model), "model", "trimmed: <reason>" (`gate` said memory is low) or "fallback" (the
    model failed or said nothing)."""
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
    return (line, "model") if line else (opening, "fallback")


def spoken_line(
    reply: str, client: Generator | None, gate: Callable[[], str | None] | None = None
) -> str:
    """The words to say for `reply`: as-is if short, else the model's gist, else its opening."""
    return spoken(reply, client, gate)[0]
