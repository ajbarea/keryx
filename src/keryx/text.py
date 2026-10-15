"""Turn a markdown reply into plain text a TTS voice can read."""

from __future__ import annotations

import re

_FENCE = re.compile(r"^\s*(```|~~~)")
_TABLE_ROW = re.compile(r"^\s*\|")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_QUOTE = re.compile(r"^\s*>\s?")

_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")
_INLINE_CODE = re.compile(r"`([^`]*)`")
# A git commit SHA read aloud is noise ("four eight one eight oh three e"); say "a commit".
# 7 to 40 hex digits as a whole token, with at least one a-f letter and one digit, so plain
# numbers (1234567) and hex-looking words (deadbed) are left alone.
_SHA = re.compile(r"(?<!\w)(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,40}(?!\w)")
# "#123" reads as "hash 123"; after a PR/issue word the "#" just goes, else say "number".
_TICKET_LABELLED = re.compile(r"(?i)\b(PR|pull request|issue)\s*#(\d+)\b")
_TICKET_BARE = re.compile(r"(?<!\w)#(\d+)(?!\w)")
# Emphasis markers hug a word on both sides; a lone `*` in `*.py` does not.
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC = re.compile(r"(?<![\w*])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*])")
# A path is rooted (`/`, `~/`, `./`) or ends in a file name with a letter extension, so
# `client/server`, `and/or` and `10/01/2026` stay; line suffixes like `:42` go too.
_PATH = re.compile(
    r"(?:(?<![\w.~/])(?:~|\.{1,2})?/(?:[\w.@-]+/)*([\w@-]+(?:\.[\w@-]+)*)"
    r"|(?:[\w.@-]+/)+([\w@-]+(?:\.[\w@-]+)*\.[A-Za-z]\w*))"
    r"(?::\d+(?::\d+)?)?(?![\w/])"
)
_SYMBOLS = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")
_SPACES = re.compile(r"\s+")

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=\S)")


def _inline(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("a link", text)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _SHA.sub("a commit", text)
    text = _TICKET_LABELLED.sub(r"\1 \2", text)
    text = _TICKET_BARE.sub(r"number \1", text)
    text = _PATH.sub(lambda m: m.group(1) or m.group(2), text)
    text = _BOLD.sub(r"\2", text)
    text = _ITALIC.sub(r"\2", text)
    text = _SYMBOLS.sub("", text)
    return _SPACES.sub(" ", text).strip()


def clean_for_speech(markdown: str) -> str:
    """Drop code, tables and headings; flatten the rest to spoken sentences."""
    parts: list[str] = []
    in_fence = False
    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or _TABLE_ROW.match(line) or _RULE.match(line) or _HEADING.match(line):
            continue
        is_item = bool(_BULLET.match(line))
        line = _QUOTE.sub("", _BULLET.sub("", line))
        line = _inline(line)
        if not line:
            continue
        if is_item and line[-1] not in ".!?:":
            line += "."
        parts.append(line)
    return " ".join(parts)


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def first_sentences(text: str, max_chars: int) -> str:
    """Whole leading sentences up to `max_chars`; a too-long first one is cut on a word."""
    out = ""
    for sentence in split_sentences(text):
        candidate = f"{out} {sentence}".strip()
        if len(candidate) > max_chars:
            break
        out = candidate
    if out:
        return out
    return text[:max_chars].rsplit(" ", 1)[0].strip()
