"""How to say words Kokoro gets wrong, such as repo names: `ajsoftworks` as `AJ soft works`.

Kept in `$XDG_CONFIG_HOME/keryx/pronounce.json` as `{"word": "how to say it"}`, matched as a
whole word without regard to case, and reread whenever the file changes. A saying written
between slashes is phonemes, for sounds no English spelling reaches: `techne` as `/texni/`
(stress marks go before the stressed vowel, as espeak writes them).
Phonemes reach the voice between `PHONEMES_OPEN` and `PHONEMES_CLOSE`.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Callable
from pathlib import Path

from keryx.config import config_dir

PHONEMES_OPEN, PHONEMES_CLOSE = "\u27e6", "\u27e7"  # ⟦ ⟧, which replies never contain
_SLASHED = re.compile(r"/([^/]+)/")


def phonemes(saying: str) -> str | None:
    """The phonemes in a saying written as `/.../`, else None."""
    m = _SLASHED.fullmatch(saying.strip())
    return m.group(1).strip() if m else None


def spoken(saying: str) -> str:
    """What replaces the word in the text handed to the voice."""
    ipa = phonemes(saying)
    return saying if ipa is None else f"{PHONEMES_OPEN}{ipa}{PHONEMES_CLOSE}"


def lexicon_path() -> Path:
    return config_dir() / "pronounce.json"


def load(path: Path | None = None, strict: bool = False) -> dict[str, str]:
    """The saved words; a missing file is empty. An unreadable one is empty too, or with
    `strict` a ValueError, so nothing is saved over words that could not be read."""
    path = path or lexicon_path()
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        if strict:
            raise ValueError(f"{path} could not be read ({exc}); fix or remove it") from exc
        return {}
    if not isinstance(raw, dict):
        if strict:
            raise ValueError(f"{path} must hold one JSON object; fix or remove it")
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, str) and str(k).strip()}


def save(words: dict[str, str], path: Path | None = None) -> None:
    path = path or lexicon_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(sorted(words.items())), indent=2) + "\n")
    tmp.replace(path)


def same_word(words: dict[str, str], word: str) -> str | None:
    """The saved spelling of `word`, which matches without regard to case."""
    return next((w for w in words if w.casefold() == word.casefold()), None)


def compile_words(words: dict[str, str]) -> Callable[[str], str]:
    """A rewriter for `words`, longest first. Each word is its own named group, so the
    replacement is found by group, not by mapping the matched text's case back to a key."""
    if not words:
        return lambda text: text
    ordered = sorted(words, key=len, reverse=True)
    says = {f"w{i}": spoken(words[w]) for i, w in enumerate(ordered)}
    pattern = re.compile(
        "|".join(rf"(?P<w{i}>(?<!\w){re.escape(w)}(?!\w))" for i, w in enumerate(ordered)),
        re.IGNORECASE,
    )
    return lambda text: pattern.sub(lambda m: says[m.lastgroup or ""], text)


def apply(words: dict[str, str], text: str) -> str:
    return compile_words(words)(text)


class Lexicon:
    """The saved pronunciations, recompiled when the file's modification time changes."""

    def __init__(self, path: Path | None = None):
        self._path = path or lexicon_path()
        self._stamp: int | None = None
        self._rewrite: Callable[[str], str] = lambda text: text

    def __call__(self, text: str) -> str:
        stamp = None
        with contextlib.suppress(OSError):
            stamp = self._path.stat().st_mtime_ns
        if stamp != self._stamp:
            self._rewrite = compile_words(load(self._path) if stamp is not None else {})
            self._stamp = stamp
        return self._rewrite(text)
