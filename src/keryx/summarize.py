"""Shrink a reply to one or two spoken sentences with a local Ollama model."""

from __future__ import annotations

import http.client
import json
import urllib.request
from typing import Protocol

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

# Long enough to cover a working session, short enough to hand the VRAM back.
KEEP_ALIVE = "30m"

# Ollama aborts a load when its client hangs up, so this must outlast a cold load:
# 4-14 s with the model file in the page cache, 44 s read from disk (2026-10-02).
LOAD_TIMEOUT = 120.0
GENERATE_TIMEOUT = 30.0

# Replies this short are spoken as-is; anything longer goes through the model.
DIRECT_MAX_CHARS = 200
SPOKEN_MAX_CHARS = 320


class Generator(Protocol):
    def generate(self, prompt: str, system: str) -> str: ...


class OllamaClient:
    def __init__(
        self,
        model: str,
        host: str = "http://localhost:11434",
        timeout: float = GENERATE_TIMEOUT,
        load_timeout: float = LOAD_TIMEOUT,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.load_timeout = load_timeout

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
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": 0.2, "num_predict": 96},
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
        self._load(KEEP_ALIVE)

    def unload(self) -> None:
        """Hand the model's VRAM back now instead of when `KEEP_ALIVE` runs out."""
        self._load(0)

    def _load(self, keep_alive: str | int) -> None:
        body = {"model": self.model, "keep_alive": keep_alive}
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.load_timeout) as resp:
            resp.read()


def _framed(message: str) -> str:
    return f"Message to rewrite:\n<message>\n{message}\n</message>"


def spoken_line(reply: str, client: Generator | None) -> str:
    """The words to say for `reply`: as-is if short, else the model's gist, else its opening."""
    cleaned = clean_for_speech(reply)
    if len(cleaned) <= DIRECT_MAX_CHARS or client is None:
        return first_sentences(cleaned, SPOKEN_MAX_CHARS)
    try:
        out = client.generate(_framed(cleaned), SYSTEM_PROMPT)
    except (OSError, http.client.HTTPException, KeyError, ValueError, TypeError):
        return first_sentences(cleaned, SPOKEN_MAX_CHARS)
    spoken = clean_for_speech(out).strip("\"' ")
    return first_sentences(spoken, SPOKEN_MAX_CHARS) or first_sentences(cleaned, SPOKEN_MAX_CHARS)
