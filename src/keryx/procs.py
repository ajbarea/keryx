"""Which Claude Code process a hook runs under, and whether a process is still alive.

A terminal is identified by its Claude Code process, not its session: `/clear` and resume
start new sessions in the same terminal. The id is `pid:starttime`, so a reused pid is
never mistaken for the terminal that held it.
"""

from __future__ import annotations

import os
from pathlib import Path

PROC = Path("/proc")
CLAUDE_NAMES = {"claude", "claude-code"}


def _stat(pid: int, proc: Path) -> list[str] | None:
    """Fields of /proc/<pid>/stat after the command name; None if the pid is gone."""
    try:
        raw = (proc / str(pid) / "stat").read_text()
    except OSError:
        return None
    # The command name sits in parentheses and may itself contain spaces or ')'.
    return raw[raw.rfind(")") + 2 :].split()


def _is_claude(pid: int, proc: Path) -> bool:
    try:
        if (proc / str(pid) / "comm").read_text().strip() in CLAUDE_NAMES:
            return True
        argv = (proc / str(pid) / "cmdline").read_bytes().split(b"\0")
    except OSError:
        return False
    # An npm install runs as `node .../@anthropic-ai/claude-code/cli.js`.
    return any(
        part in CLAUDE_NAMES for a in argv[:2] for part in Path(a.decode(errors="replace")).parts
    )


def terminal_id(pid: int | None = None, proc: Path = PROC) -> str:
    """`pid:starttime` of the nearest Claude Code ancestor, or "" outside one."""
    pid = os.getpid() if pid is None else pid
    for _ in range(32):
        fields = _stat(pid, proc)
        if fields is None:
            return ""
        if _is_claude(pid, proc):
            return f"{pid}:{fields[19]}"  # stat field 22, starttime
        pid = int(fields[1])  # stat field 4, ppid
        if pid < 1:  # pid 1 itself is checked: in a container Claude Code can be init
            return ""
    return ""


def is_alive(terminal: str, proc: Path = PROC) -> bool | None:
    """Whether the process behind a `terminal_id` still runs; None if `terminal` is not one."""
    pid, _, start = terminal.partition(":")
    if not (pid.isdigit() and start.isdigit()):
        return None
    fields = _stat(int(pid), proc)
    # A zombie (state Z) has exited and only waits for its parent to reap it.
    return fields is not None and fields[0] != "Z" and fields[19] == start
