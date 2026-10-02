"""Claude Code hook entry point: map a hook event to a daemon request."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from keryx import __version__

# `claude -p` and the Agent SDK run with an `sdk-*` entrypoint; nobody is listening.
# Interactive surfaces (terminal, IDE extensions, desktop app) use other values.
HEADLESS_PREFIX = "sdk"

SPOKEN_NOTIFICATIONS = {"permission_prompt", "elicitation_dialog", "elicitation_url_dialog"}

_CLAUDE_NEEDS = re.compile(r"^Claude (Code )?needs\b", re.IGNORECASE)


def source_name(cwd: str) -> str:
    """The repo a session works in, by its main checkout's name (worktrees included)."""
    if not cwd:
        return ""
    try:
        common = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        ).stdout.strip()
        return Path(common).parent.name
    except (subprocess.SubprocessError, OSError):
        return Path(cwd).name


def request_for(event: dict, entrypoint: str) -> dict | None:
    """The daemon request for one hook payload, or None to stay silent."""
    if entrypoint.startswith(HEADLESS_PREFIX):
        return None
    name = event.get("hook_event_name")
    session = event.get("session_id", "")
    if name == "SessionStart":
        # Start the cold load while the developer types the first prompt.
        return {"op": "warm", "version": __version__}
    if name == "UserPromptSubmit":
        # keryx's own commands must not restart the daemon or reload the model.
        if str(event.get("user_input") or event.get("prompt") or "").startswith("/keryx:"):
            return None
        prompt = event.get("prompt_id", "")
        return {"op": "stop", "session": session, "prompt": prompt, "warm": True}
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
            "source": source_name(event.get("cwd", "")),
        }
    return None


def entrypoint() -> str:
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")


def parse(stdin_text: str) -> dict:
    try:
        event = json.loads(stdin_text)
    except json.JSONDecodeError:
        return {}
    return event if isinstance(event, dict) else {}
