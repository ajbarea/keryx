import os
import threading
import time
from pathlib import Path

import pytest

from keryx import player as player_mod
from keryx.player import WindowsPlayer, windows_path


def test_windows_path():
    wav = Path("/mnt/c/Windows/Temp/keryx/keryx-0.wav")
    assert windows_path(wav) == "C:\\Windows\\Temp\\keryx\\keryx-0.wav"
    with pytest.raises(ValueError):
        windows_path(Path("/home/aj/x.wav"))


@pytest.fixture
def mute_shell(tmp_path):
    """Stands in for powershell.exe: takes commands, never answers."""
    script = tmp_path / "mute"
    script.write_text("#!/bin/sh\nexec sleep 30\n")
    os.chmod(script, 0o755)
    return str(script)


def test_a_hung_player_times_out_and_close_does_not_deadlock(mute_shell, monkeypatch):
    monkeypatch.setattr(player_mod, "REPLY_TIMEOUT", 0.2)
    p = WindowsPlayer(powershell=mute_shell)
    started = time.time()
    assert p.play(Path("/mnt/c/x.wav"), 5.0, threading.Event()) is False
    assert time.time() - started < 2
    closer = threading.Thread(target=p.close)
    closer.start()
    closer.join(2)
    assert not closer.is_alive()
