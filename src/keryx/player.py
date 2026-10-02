"""Play WAV files through Windows from WSL.

WSLg's PulseAudio sink suspends when idle and drops or hangs streams on resume
(microsoft/wslg#1392), so audio goes to the Windows side instead: one long-lived
PowerShell process owns a `System.Media.SoundPlayer` and takes `play`/`stop`
commands on stdin. The file must sit on a Windows drive; `\\\\wsl.localhost` paths
stall for seconds.
"""

from __future__ import annotations

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
                self._proc = subprocess.Popen(
                    self._cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                    cwd="/mnt/c",
                )
            assert self._proc.stdin and self._proc.stdout
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
            return self._proc.stdout.readline().strip()

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
        with self._lock:
            if self._proc is not None:
                self._proc.kill()
                self._proc = None
