"""Tell klepsydra's wall which voice is speaking: `speaking.json` in its fleet folder.

Contract: docs/speaking-signal.md. Every failure is logged at debug and swallowed; speech
never waits on or fails because of this file.
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path

import numpy as np

log = logging.getLogger("keryx")

SCHEMA = 1
FILE = "speaking.json"
ENVELOPE_HZ = 20
APP_ID = "dev.ajsoftworks.klepsydra"
CLOSE_WAIT = 0.5  # seconds `close` waits for the writer before abandoning it
STALE_TMP = 60.0  # seconds before another run's temp file counts as litter


def envelope(samples: np.ndarray, rate: int, hz: int = ENVELOPE_HZ) -> list[float]:
    """RMS level at `hz` windows a second, scaled so the loudest window is 1.0, 2 decimals.

    ceil(duration * hz) values; silence is all 0.0. A short last window uses what is left.
    """
    if samples.size == 0 or rate <= 0:
        return []
    n = math.ceil(samples.size * hz / rate)
    edges = np.minimum((np.arange(n + 1) * rate / hz).astype(np.int64), samples.size)
    edges[-1] = samples.size
    clean = np.nan_to_num(samples.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    squares = np.square(clean)
    sums = np.add.reduceat(squares, edges[:-1])
    counts = np.maximum(np.diff(edges), 1)
    rms = np.sqrt(sums / counts)
    top = rms.max()
    if not top > 1e-9:
        return [0.0] * n
    return [round(float(v), 2) for v in rms / top]


def fleet_dir(env: Mapping[str, str] | None = None, osrelease: str | None = None) -> Path | None:
    """klepsydra's fleet folder, chosen as hooks/klepsydra-fleet.sh chooses its own."""
    env = os.environ if env is None else env
    if env.get("KLEPSYDRA_DIR"):
        return Path(env["KLEPSYDRA_DIR"]) / "fleet"
    if osrelease is None:
        with contextlib.suppress(OSError):
            osrelease = Path("/proc/sys/kernel/osrelease").read_text()
    if osrelease and ("Microsoft" in osrelease or "microsoft" in osrelease):  # as the hook's [Mm]
        user = env.get("USER")
        return Path(f"/mnt/c/Users/{user}/AppData/Local/{APP_ID}/fleet") if user else None
    data = env.get("XDG_DATA_HOME", "")
    if not data.startswith("/"):
        home = env.get("HOME", "")
        data = f"{home}/.local/share" if home else ""
    return Path(data) / APP_ID / "fleet" if data.startswith("/") else None


def claude_of(terminal: str) -> tuple[int, int] | None:
    """`pid`, `starttime` from a terminal key (`pid:starttime`); None for anything else."""
    pid, _, start = terminal.partition(":")
    return (int(pid), int(start)) if pid.isdigit() and start.isdigit() else None


class SpeakingSignal:
    def __init__(
        self,
        folder: Path | None,
        enabled: bool = True,
        clock: Callable[[], float] = time.time,
        background: bool = True,
    ):
        """With `background`, files are written in order by one worker thread, because a
        write to a Windows drive takes tens of milliseconds the player must not wait for."""
        self._background = background
        self._cond = threading.Condition()
        self._pending: tuple[Callable[..., None], tuple] | None = None
        self._closed = False
        self._worker: threading.Thread | None = None
        self._folder = folder
        self._enabled = enabled
        self._clock = clock
        self._lock = threading.Lock()
        self._owner: object = None
        self._sweep()
        if background:
            self._worker = threading.Thread(target=self._work, name="keryx-speaking", daemon=True)
            self._worker.start()

    def _target(self) -> Path | None:
        f = self._folder
        if not self._enabled or f is None or f.is_symlink() or not f.is_dir():
            return None
        return f / FILE

    def start(
        self,
        owner: object,
        seconds: float,
        env: list[float],
        voice: str,
        terminal: str,
        session: str,
    ) -> None:
        """A clip starts playing now: replace the file with it."""
        now = self._clock()
        self._run(self._write, owner, now, seconds, env, voice, terminal, session)

    def clear(self, owner: object = None) -> None:
        """Remove the file; with `owner`, only if that line wrote it (another's stays)."""
        self._run(self._remove, owner)

    def close(self) -> None:
        """Let the writer finish what is pending for at most `CLOSE_WAIT`, then abandon it
        (a hung drive must not hold up the daemon's exit). Later calls are dropped."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        if self._worker is not None:
            self._worker.join(CLOSE_WAIT)

    def _run(self, fn: Callable[..., None], *args: object) -> None:
        if not self._background:
            fn(*args)
            return
        with self._cond:
            if self._closed:
                return
            held = self._pending
            # A removal for one line must not displace another line's pending write.
            if (
                fn == self._remove
                and args[0] is not None
                and held is not None
                and held[0] == self._write
                and held[1][0] is not args[0]
            ):
                return
            self._pending = (fn, args)  # latest wins: only the newest state matters
            self._cond.notify_all()

    def _work(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._closed:
                    self._cond.wait()
                if self._pending is None:
                    return
                fn, args = self._pending
                self._pending = None
            fn(*args)

    def _sweep(self) -> None:
        """Delete this module's temp files left by a run that died mid-write."""
        try:
            target = self._target()
            if target is None:
                return
            cutoff = time.time() - STALE_TMP
            for f in target.parent.glob(f"{FILE}.*.tmp"):
                with contextlib.suppress(OSError):
                    if f.stat().st_mtime < cutoff:
                        f.unlink()
        except Exception as exc:
            log.debug("could not sweep %s temp files: %s", FILE, exc)

    def _write(
        self,
        owner: object,
        now: float,
        seconds: float,
        env: list[float],
        voice: str,
        terminal: str,
        session: str,
    ) -> None:
        try:
            target = self._target()
            if target is None:
                return
            doc: dict = {"v": SCHEMA, "voice": voice, "terminal": terminal}
            if (claude := claude_of(terminal)) is not None:
                doc["claude_pid"], doc["claude_start"] = claude
            if session:
                doc["session_id"] = session
            doc.update(started_at=now, ends_at=now + seconds, envelope=env)
            tmp = target.with_name(f"{FILE}.{os.getpid()}.tmp")
            with self._lock:
                try:
                    tmp.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False) + "\n")
                    os.replace(tmp, target)
                except BaseException:
                    with contextlib.suppress(OSError):
                        tmp.unlink()
                    raise
                self._owner = owner
        except Exception as exc:
            log.debug("could not write %s: %s", FILE, exc)

    def _remove(self, owner: object) -> None:
        try:
            target = self._target()
            if target is None:
                return
            with self._lock:
                if owner is not None and owner is not self._owner:
                    return
                self._owner = None
                target.unlink(missing_ok=True)
        except Exception as exc:
            log.debug("could not remove %s: %s", FILE, exc)
