"""Play WAV files through Windows from WSL.

WSLg's PulseAudio sink suspends when idle and drops or hangs streams on resume
(microsoft/wslg#1392), so audio goes to the Windows side instead: one long-lived
PowerShell process owns a `System.Media.SoundPlayer` and takes `play`/`stop`
commands on stdin. The file must sit on a Windows drive; `\\\\wsl.localhost` paths
stall for seconds.
"""

from __future__ import annotations

import select
import subprocess
import threading
from pathlib import Path
from typing import Protocol

_PS_LOOP = r"""
$ErrorActionPreference = 'Continue'
$p = New-Object System.Media.SoundPlayer
while ($null -ne ($line = [Console]::In.ReadLine())) {
    if ($line.StartsWith('play ')) {
        $p.Stop()
        try {
            $p.SoundLocation = $line.Substring(5); $p.Load(); $p.Play()
            [Console]::Out.WriteLine('ok')
        } catch { [Console]::Out.WriteLine('err ' + $_.Exception.Message) }
    } elseif ($line -eq 'stop') {
        $p.Stop(); [Console]::Out.WriteLine('ok')
    }
    [Console]::Out.Flush()
}
"""


REPLY_TIMEOUT = 10.0  # seconds; a play or stop answers in milliseconds


class Player(Protocol):
    def play(self, wav: Path, seconds: float, interrupt: threading.Event) -> bool: ...
    def stop(self) -> None: ...


def windows_path(path: Path) -> str:
    """`/mnt/c/Users/x` -> `C:\\Users\\x`; only Windows-drive paths are playable."""
    parts = path.resolve().parts
    if len(parts) < 3 or parts[1] != "mnt" or len(parts[2]) != 1:
        raise ValueError(f"{path} is not on a Windows drive")
    return f"{parts[2].upper()}:\\" + "\\".join(parts[3:])


class WindowsPlayer:
    def __init__(self, powershell: str = "powershell.exe"):
        self._cmd = [powershell, "-NoProfile", "-NonInteractive", "-Command", _PS_LOOP]
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def _send(self, line: str) -> str:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
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

    def close(self) -> None:
        # No lock: a play stuck in `_send` holds it, and kill() is what unsticks it.
        proc = self._proc
        if proc is not None:
            proc.kill()
