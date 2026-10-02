"""Play WAV files through Windows from WSL.

WSLg's PulseAudio sink suspends when idle and drops or hangs streams on resume
(microsoft/wslg#1392), so audio goes to the Windows side instead: one long-lived
PowerShell process owns a `System.Media.SoundPlayer` and takes `play`/`stop`
commands on stdin. The file must sit on a Windows drive; `\\\\wsl.localhost` paths
stall for seconds.

The same process ducks other apps (Spotify by default) while keryx speaks, through
`ducker.cs`, which it compiles once at start. It restores anything a crashed predecessor
left ducked when it starts, and restores again when its stdin closes.
"""

from __future__ import annotations

import contextlib
import logging
import select
import subprocess
import threading
from importlib import resources
from pathlib import Path
from typing import Protocol

_PS_LOOP = r"""
$ErrorActionPreference = 'Continue'
$p = New-Object System.Media.SoundPlayer
$state = '@STATE@'
$ducker = $false
$duckError = 'not configured'
if ($state) {
    try {
        Add-Type -Path '@SOURCE@'; $ducker = $true; [void][KeryxDucker]::Unduck($state)
    } catch { $duckError = $_.Exception.Message -replace '\s+', ' ' }
}
try {
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ($line.StartsWith('play ')) {
            $p.Stop()
            try {
                $p.SoundLocation = $line.Substring(5); $p.Load(); $p.Play()
                [Console]::Out.WriteLine('ok')
            } catch { [Console]::Out.WriteLine('err ' + $_.Exception.Message) }
        } elseif ($line -eq 'stop') {
            $p.Stop(); [Console]::Out.WriteLine('ok')
        } elseif ($line.StartsWith('duck ')) {
            $f = $line.Split(' ', 3)
            if ($ducker) {
                try {
                    $ratio = [single]::Parse($f[1], [Globalization.CultureInfo]::InvariantCulture)
                    [Console]::Out.WriteLine('ok ' + [KeryxDucker]::Duck($state, $f[2], $ratio))
                } catch {
                    $why = $_.Exception.Message -replace '\s+', ' '
                    [Console]::Out.WriteLine("ok 0 failed: $why")
                }
            } else { [Console]::Out.WriteLine("ok 0 disabled: $duckError") }
        } elseif ($line -eq 'unduck') {
            $n = 0
            if ($ducker) { try { $n = [KeryxDucker]::Unduck($state) } catch {} }
            [Console]::Out.WriteLine("ok $n")
        }
        [Console]::Out.Flush()
    }
} finally {
    if ($ducker) { try { [void][KeryxDucker]::Unduck($state) } catch {} }
}
"""

log = logging.getLogger("keryx")

DUCKER_SOURCE = "keryx-ducker.cs"
DUCK_STATE = "keryx-ducked.txt"


REPLY_TIMEOUT = 10.0  # seconds; a play or stop answers in milliseconds
CLOSE_GRACE = 2.0  # seconds for the loop to restore ducked volumes on close


def _quoted(text: str) -> str:
    """For a single-quoted PowerShell literal, where a quote is written twice."""
    return text.replace("'", "''")


class Player(Protocol):
    def play(self, wav: Path, seconds: float, interrupt: threading.Event) -> bool: ...
    def stop(self) -> None: ...
    def duck(self) -> None: ...
    def unduck(self) -> None: ...


def windows_path(path: Path) -> str:
    """`/mnt/c/Users/x` -> `C:\\Users\\x`; only Windows-drive paths are playable."""
    parts = path.resolve().parts
    if len(parts) < 3 or parts[1] != "mnt" or len(parts[2]) != 1:
        raise ValueError(f"{path} is not on a Windows drive")
    return f"{parts[2].upper()}:\\" + "\\".join(parts[3:])


class WindowsPlayer:
    def __init__(
        self,
        powershell: str = "powershell.exe",
        audio_dir: Path | None = None,
        duck_apps: tuple[str, ...] = (),
        duck_ratio: float = 1.0,
    ):
        """Ducks `duck_apps` (process names) to `duck_ratio` of their volume while speaking;
        ducking needs `audio_dir` on a Windows drive for its source and state files."""
        state = source = ""
        self._duck = ""
        if audio_dir is not None and duck_apps and duck_ratio < 1:
            with contextlib.suppress(OSError, ValueError):
                audio_dir.mkdir(parents=True, exist_ok=True)
                code = resources.files("keryx").joinpath("ducker.cs").read_text()
                (audio_dir / DUCKER_SOURCE).write_text(code)
                source = windows_path(audio_dir / DUCKER_SOURCE)
                state = windows_path(audio_dir / DUCK_STATE)
                self._duck = f"duck {duck_ratio:g} {','.join(duck_apps)}"
        script = _PS_LOOP.replace("@STATE@", _quoted(state)).replace("@SOURCE@", _quoted(source))
        self._cmd = [powershell, "-NoProfile", "-NonInteractive", "-Command", script]
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._ducked = False  # between duck() and unduck()
        self._warned = False

    def _send(self, line: str) -> str:
        with self._lock:
            fresh = self._proc is None or self._proc.poll() is not None
            if fresh:
                try:
                    self._proc = subprocess.Popen(
                        self._cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        bufsize=1,
                        # A Windows cwd keeps powershell.exe from warning about UNC paths.
                        cwd="/mnt/c" if Path("/mnt/c").is_dir() else None,
                    )
                except OSError:
                    self._proc = None
                    return "err"
            proc = self._proc
            assert proc is not None
            # A fresh loop restores volumes on start, so speech already ducked must duck again.
            redo = fresh and self._ducked and line not in (self._duck, "unduck")
            if redo and self._exchange(proc, self._duck) == "err":
                return "err"
            return self._exchange(proc, line)

    def _exchange(self, proc: subprocess.Popen[str], line: str) -> str:
        assert proc.stdin and proc.stdout
        try:
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
            ready, _, _ = select.select([proc.stdout], [], [], REPLY_TIMEOUT)
            if not ready:
                raise TimeoutError(f"powershell did not answer {line.split()[0]!r}")
            return proc.stdout.readline().strip()
        except (OSError, TimeoutError):
            proc.kill()  # a fresh process starts on the next command
            self._proc = None
            return "err"

    def play(self, wav: Path, seconds: float, interrupt: threading.Event) -> bool:
        """Start `wav` and block for its length; False if interrupted or it failed to start."""
        if self._send(f"play {windows_path(wav)}") != "ok":
            return False
        if interrupt.wait(seconds):
            self.stop()
            return False
        return True

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._send("stop")

    def duck(self) -> None:
        if not self._duck:
            return
        self._ducked = True
        reply = self._send(self._duck)
        if (" disabled: " in reply or " failed: " in reply) and not self._warned:
            log.warning("could not duck other apps: %s", reply.split(": ", 1)[1])
            self._warned = True

    def unduck(self) -> None:
        # Sent even to a dead player: the fresh one `_send` starts restores on its own start.
        if self._duck:
            self._ducked = False
            self._send("unduck")

    def close(self) -> None:
        # No lock: a play stuck in `_send` holds it, and kill() is what unsticks it. Closing
        # stdin first lets the loop's `finally` restore ducked volumes before the kill.
        proc = self._proc
        if proc is None:
            return
        with contextlib.suppress(OSError, ValueError, subprocess.TimeoutExpired):
            if proc.stdin:
                proc.stdin.close()
            proc.wait(CLOSE_GRACE)
        with contextlib.suppress(OSError):
            proc.kill()
