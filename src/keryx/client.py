"""Talk to the daemon from a hook or the CLI; kept free of heavy imports."""

from __future__ import annotations

import contextlib
import fcntl
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

from keryx.config import cache_dir, socket_path


def read_all(conn: socket.socket) -> bytes:
    chunks = []
    while chunk := conn.recv(65536):
        chunks.append(chunk)
    return b"".join(chunks)


def send(request: dict, sock_path: Path | None = None, timeout: float = 5.0) -> dict:
    """Send one request; raises OSError if no daemon is listening."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path or socket_path()))
        s.sendall(json.dumps(request).encode())
        s.shutdown(socket.SHUT_WR)
        return json.loads(read_all(s) or b"{}")


def spawn() -> subprocess.Popen:
    """Start a detached daemon that outlives the hook process."""
    log_file = cache_dir() / "daemon.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "ab") as out:
        return subprocess.Popen(
            [sys.executable, "-m", "keryx", "daemon"],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=out,
            start_new_session=True,
            cwd="/",  # don't pin the session's working directory for hours
        )


# The daemon's exit status when another daemon holds the lock (EX_TEMPFAIL); that one may
# be a retiring daemon that has not released it yet.
LOCK_BUSY_EXIT = 75
RETIRE_WAIT_SECONDS = 10.0

# A first run downloads ~350 MB of model files before the socket binds; hooks are async,
# so waiting costs the session nothing.
SPAWN_WAIT_SECONDS = 900.0


def send_or_spawn(request: dict, wait: float = SPAWN_WAIT_SECONDS) -> dict:
    """Send, starting the daemon first if none is running."""
    try:
        return send(request)
    except (FileNotFoundError, ConnectionRefusedError):
        pass
    lock = cache_dir() / "spawn.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            return send(request)
        except (FileNotFoundError, ConnectionRefusedError):
            daemon = spawn()
        deadline = time.monotonic() + wait
        while True:
            try:
                return send(request)
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() > deadline:
                    raise
                status = daemon.poll()
                if status == LOCK_BUSY_EXIT:
                    daemon = spawn()  # a retiring daemon still held the lock; try again
                elif status is not None:
                    raise  # exited for good (turned off, or failed to start)
                time.sleep(0.2)


def warm_current(request: dict) -> dict:
    """Send a `warm`, first replacing a daemon from another keryx version."""
    reply = send_or_spawn(request)
    if reply.get("version") != request["version"]:
        return replace_daemon(request, reply)
    return reply


def replace_daemon(request: dict, reply: dict, sock_path: Path | None = None) -> dict:
    """Retire a daemon from another keryx version and send `request` to a fresh one.

    A daemon keeps the code it started with. One from 0.1.0 has no `warm` op, so any reply
    without the caller's version means an older daemon.
    """
    sock_path = sock_path or socket_path()
    if not reply.get("quit"):
        with contextlib.suppress(OSError):
            send({"op": "quit"}, sock_path)
    deadline = time.monotonic() + RETIRE_WAIT_SECONDS
    while sock_path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return send_or_spawn(request)
