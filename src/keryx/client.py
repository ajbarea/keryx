"""Talk to the daemon from a hook or the CLI; kept free of heavy imports."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
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
    """Start a detached daemon that outlives the hook process.

    It logs to `daemon.log` itself. What only a dying process writes to stderr (an import
    error, a native abort) goes to `daemon.stderr`, private and restarted with each daemon.
    """
    err = cache_dir() / "daemon.stderr"
    err.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(err, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)  # a file from an older version may be wider
    try:
        return subprocess.Popen(
            [sys.executable, "-m", "keryx", "daemon"],
            stdin=subprocess.DEVNULL,
            stdout=fd,
            stderr=fd,
            start_new_session=True,
            cwd="/",  # don't pin the session's working directory for hours
        )
    finally:
        os.close(fd)


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


def current(request: dict) -> dict:
    """Send a `warm` or `ping`, replacing a daemon from an older keryx first."""
    reply = send_or_spawn(request)
    if predates(reply, request["version"]):
        return replace_daemon(request, reply)
    return reply


def predates(reply: dict, ours: str) -> bool:
    """Whether the daemon that sent `reply` runs an older keryx than `ours`.

    Only a daemon from before versions are reported leaves the version out of a good reply
    or refuses `warm` as an unknown op. A current one that failed this request, or an empty
    reply, says nothing about its age and is left running.
    """
    from keryx import older

    if reply.get("version"):
        return older(reply["version"], ours)
    return reply.get("ok") is True or str(reply.get("error", "")).startswith("unknown op")


def replace_daemon(request: dict, reply: dict, sock_path: Path | None = None) -> dict:
    """Retire a daemon from another keryx version and send `request` to a fresh one.

    A daemon keeps the code it started with. One from 0.1.0 has no `warm` op and answers
    without a version (see `predates`).
    """
    sock_path = sock_path or socket_path()
    if not reply.get("quit"):
        with contextlib.suppress(OSError):
            send({"op": "quit"}, sock_path)
    deadline = time.monotonic() + RETIRE_WAIT_SECONDS
    while sock_path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return send_or_spawn(request)
