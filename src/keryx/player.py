"""Play WAV files through Windows from WSL.

WSLg's PulseAudio sink suspends when idle and drops or hangs streams on resume
(microsoft/wslg#1392), so audio goes to the Windows side instead: one long-lived
PowerShell process plays each WAV through MCI (winmm) and takes `play`/`mode`/`stop`
commands on stdin. The file must sit on a Windows drive; `\\\\wsl.localhost` paths
stall for seconds.

A clip is done when MCI says it stopped, not when its length has passed since `play`
answered: Windows starts a clip up to ~150 ms late, about as long as the silence that
ends a sentence, so a timer cut that pause off and ran sentences together.

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
import time
from importlib import resources
from pathlib import Path
from typing import Protocol

_PS_LOOP = r"""
$ErrorActionPreference = 'Continue'
$mciError = ''
try {
    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices; using System.Text;
public static class KeryxMci {
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    static extern int mciSendString(string cmd, StringBuilder ret, int size, System.IntPtr hwnd);
    public static string Send(string command) {
        var ret = new StringBuilder(128);
        int rc = mciSendString(command, ret, ret.Capacity, System.IntPtr.Zero);
        return rc == 0 ? ret.ToString() : "mci error " + rc;
    }
}
'@
} catch { $mciError = $_.Exception.Message -replace '\s+', ' ' }
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
        if ($mciError -and ($line.StartsWith('play ') -or $line -eq 'mode')) {
            [Console]::Out.WriteLine('err MCI unavailable: ' + $mciError)
        } elseif ($line.StartsWith('play ')) {
            [void][KeryxMci]::Send('close keryx')
            $r = [KeryxMci]::Send('open "' + $line.Substring(5) + '" type waveaudio alias keryx')
            if (-not $r.StartsWith('mci error')) { $r = [KeryxMci]::Send('play keryx') }
            if ($r.StartsWith('mci error')) { [Console]::Out.WriteLine('err ' + $r) }
            else { [Console]::Out.WriteLine('ok') }
        } elseif ($line -eq 'mode') {
            $mode = [KeryxMci]::Send('status keryx mode')
            # A finished clip is closed at once, so its WAV is free to be written again.
            if ($mode -eq 'stopped') { [void][KeryxMci]::Send('close keryx') }
            [Console]::Out.WriteLine('ok ' + $mode)
        } elseif ($line -eq 'stop') {
            [void][KeryxMci]::Send('stop keryx'); [void][KeryxMci]::Send('close keryx')
            [Console]::Out.WriteLine('ok')
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
EARLY = 0.25  # seconds before a clip's end to start asking whether it has finished
POLL = 0.03  # seconds between those asks
OVERRUN = 3.0  # seconds past its end after which a clip still "playing" is stopped
FINISHED = {"ok stopped"}
# MCI refuses a path of this many characters or more, even when given a relative name.
MCI_PATH_LIMIT = 128
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
        with contextlib.suppress(ValueError):
            longest = windows_path(audio_dir / "keryx-0.wav") if audio_dir else ""
            if len(longest) >= MCI_PATH_LIMIT:
                log.warning(
                    "audio_dir %s is too long for Windows' MCI (%d characters or more); "
                    "nothing will play until it is shorter",
                    audio_dir,
                    MCI_PATH_LIMIT,
                )
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
        """Play `wav` to its end; False if interrupted or it failed to start."""
        reply = self._send(f"play {windows_path(wav)}")
        if reply != "ok":
            log.warning("could not play %s: %s", wav.name, reply)
            return False
        if interrupt.wait(max(0.0, seconds - EARLY)):
            self.stop()
            return False
        deadline = time.monotonic() + EARLY + OVERRUN
        # Only "stopped" is done: a transient mode such as "not ready" may still be sounding.
        while (mode := self._send("mode")) not in FINISHED:
            if not mode.startswith("ok") or mode.startswith("ok mci error"):
                if not interrupt.is_set():  # a stop from elsewhere closes the clip
                    log.warning("could not ask whether %s finished: %s", wav.name, mode)
                break
            if time.monotonic() > deadline:
                log.warning("%s still %s %.1fs past its end; stopped", wav.name, mode[3:], OVERRUN)
                self.stop()
                break
            if interrupt.wait(POLL):
                self.stop()
                break
        return not interrupt.is_set()

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
