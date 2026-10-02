"""Talk to the daemon from a hook or the CLI; kept free of heavy imports."""

from __future__ import annotations

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
                # Exited (turned off, or an old daemon still held the lock): it never binds.
                if daemon.poll() is not None or time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
