"""Claude Code hook entry point: map a hook event to a daemon request."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from keryx import version
from keryx.procs import terminal_id

# `claude -p` and the Agent SDK run with an `sdk-*` entrypoint; nobody is listening.
# Interactive surfaces (terminal, IDE extensions, desktop app) use other values.
HEADLESS_PREFIX = "sdk"

SPOKEN_NOTIFICATIONS = {"permission_prompt", "elicitation_dialog", "elicitation_url_dialog"}

_CLAUDE_NEEDS = re.compile(r"^Claude (Code )?needs\b", re.IGNORECASE)

# A whole prompt asking to hear the last line again: "say that again", "sorry, come again?",
# "I didn't catch that". Anything more ("say that again in Spanish") goes to Claude.
_REPLAY = re.compile(
    r"^\s*(?:(?:hey|ok|okay|sorry|um|uh|please|can you|could you|would you|claude)[\s,]+)*"
    r"(?:say (?:that|it) again|say (?:that|it) once more|repeat (?:that|it|yourself)(?: again)?"
    r"|come again|what did you (?:just )?say"
    r"|(?:i )?(?:didn'?t|did not) (?:catch|hear) (?:that|it|you)"
    r"|pardon(?: me)?)"
    r"(?:[\s,]+please)?\s*[.!?]*\s*$",
    re.IGNORECASE,
)


# Words `bin/keryx-replay` screens for before starting Python; every phrase _REPLAY accepts
# contains one (a test runs them all through the screen).
SCREEN_WORDS = ("again", "more", "repeat", "pardon", "catch", "hear", "what did you")


# Longer prompts are never replay requests. The shell screen allows `SCREEN_SLACK` more
# characters either side of its word, for JSON escapes, so it never turns one away.
MAX_REPLAY_CHARS = 60
SCREEN_SLACK = 20


def is_replay(prompt: str) -> bool:
    if len(prompt) > MAX_REPLAY_CHARS:
        return False
    # Dictation and autocorrect write the apostrophe in "didn't" as U+2019.
    return bool(_REPLAY.match(prompt.replace("\u2019", "'")))


def prompt_text(event: dict) -> str:
    return str(event.get("user_input") or event.get("prompt") or "")


# `/keryx on` and the rest come from the hooks module; `/keryx:pronounce` is a skill.
KERYX_COMMAND = re.compile(r"/keryx(?::|\s|$)")


def is_keryx_command(prompt: str) -> bool:
    return KERYX_COMMAND.match(prompt.lstrip()) is not None


def is_replay_event(event: dict, entrypoint: str) -> bool:
    """Whether a hook payload is an interactive prompt asking to hear the last line again."""
    return not entrypoint.startswith(HEADLESS_PREFIX) and is_replay(prompt_text(event))


def source_name(cwd: str) -> str:
    """The repo a session works in, by its main checkout's name (worktrees included).

    Read from `.git` directly rather than through `git`, so a prompt's stop never waits on
    a subprocess. A worktree's `.git` file names its git dir, whose `commondir` leads to
    the main checkout's `.git` (gitrepository-layout).
    """
    if not cwd:
        return ""
    here = Path(cwd)
    for folder in (here, *here.parents):
        dotgit = folder / ".git"
        try:
            if dotgit.is_dir():
                return folder.name
            if dotgit.is_file():
                text = dotgit.read_text().strip()
                if not text.startswith("gitdir:"):
                    return folder.name
                gitdir = (folder / text.removeprefix("gitdir:").strip()).resolve()
                common = gitdir / "commondir"
                if not common.is_file():
                    return folder.name  # a submodule: its own checkout names it
                return (gitdir / common.read_text().strip()).resolve().parent.name
        except OSError:
            break
    return here.name


def request_for(event: dict, entrypoint: str) -> dict | None:
    """The daemon request for one hook payload, or None to stay silent.

    Requests name their terminal, which holds the voice: `/clear` and resume start new
    sessions in it.
    """
    if entrypoint.startswith(HEADLESS_PREFIX):
        return None
    name = event.get("hook_event_name")
    session = event.get("session_id", "")
    if name == "SessionStart":
        # Start the cold load while the developer types the first prompt; hold a voice.
        return {
            "op": "warm",
            "version": version(),
            "session": session,
            "terminal": terminal_id(),
            "source": source_name(event.get("cwd", "")),
        }
    if name == "UserPromptSubmit":
        # keryx's own commands must not restart the daemon or reload the model.
        if is_keryx_command(prompt_text(event)):
            return None
        return prompt_request(event, replay=is_replay_event(event, entrypoint))
    if name == "Stop":
        text = event.get("last_assistant_message") or ""
        if not text.strip():
            return None
        return {
            "op": "say",
            "kind": "reply",
            "text": text,
            "session": session,
            "prompt": event.get("prompt_id", ""),
            "terminal": terminal_id(),
            "source": source_name(event.get("cwd", "")),
        }
    if name == "Notification" and event.get("notification_type") in SPOKEN_NOTIFICATIONS:
        message = (event.get("message") or "").strip()
        if not message:
            return None
        return {
            "op": "say",
            "kind": "notice",
            "text": _CLAUDE_NEEDS.sub("I need", message),
            "session": session,
            "terminal": terminal_id(),
            "source": source_name(event.get("cwd", "")),
        }
    return None


def prompt_request(event: dict, replay: bool = False) -> dict:
    """The `stop` request for a prompt: cut off the speech, record the prompt, load the model.

    A replay request holds back all three. The synchronous hook may answer it with a replay
    the stop would cut off, and no turn follows an answered one, so its prompt is not the
    session's latest and the summarizer has nothing to load for. When nothing is replayed,
    Claude answers and that hook sends the full request. If that hook times out instead,
    the reply to this prompt is dropped as stale; a rare loss, preferred to tracking prompt
    order across asynchronous hooks.
    """
    request = {
        "op": "stop",
        "session": event.get("session_id", ""),
        "terminal": terminal_id(),
        "source": source_name(event.get("cwd", "")),
    }
    if replay:
        return {**request, "interrupt": False}
    return {**request, "prompt": event.get("prompt_id", ""), "warm": True}


def entrypoint() -> str:
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")


def parse(stdin_text: str) -> dict:
    try:
        event = json.loads(stdin_text)
    except json.JSONDecodeError:
        return {}
    return event if isinstance(event, dict) else {}
