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


def test_a_missing_powershell_fails_the_play_instead_of_raising(tmp_path):
    p = WindowsPlayer(powershell=str(tmp_path / "no-such-shell"))
    assert p.play(Path("/mnt/c/x.wav"), 1.0, threading.Event()) is False


@pytest.fixture
def echo_shell(tmp_path):
    """Stands in for powershell.exe: logs each command, answers ok, logs eof on close."""
    log = tmp_path / "commands.log"
    script = tmp_path / "echo"
    loop = f'while read -r line; do echo "$line" >> {log}; echo ok; done'
    script.write_text(f"#!/bin/sh\n{loop}\necho eof >> {log}\n")
    os.chmod(script, 0o755)
    return str(script), log


@pytest.fixture
def on_windows_drive(monkeypatch):
    monkeypatch.setattr(player_mod, "windows_path", lambda p: "C:\\\\k\\\\" + p.name)


def test_duck_and_unduck_send_the_configured_apps(echo_shell, tmp_path, on_windows_drive):
    shell, log = echo_shell
    p = WindowsPlayer(shell, tmp_path, duck_apps=("Spotify", "chrome"), duck_ratio=0.25)
    p.duck()
    p.unduck()
    p.close()
    assert log.read_text().splitlines() == ["duck 0.25 Spotify,chrome", "unduck", "eof"]
    assert (tmp_path / player_mod.DUCKER_SOURCE).read_text().startswith("// Lowers")


def test_close_lets_the_loop_restore_volumes_before_the_kill(
    echo_shell, tmp_path, on_windows_drive
):
    shell, log = echo_shell
    p = WindowsPlayer(shell, tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    p.duck()
    p.close()
    assert log.read_text().splitlines()[-1] == "eof"  # stdin closed, so `finally` ran


@pytest.mark.parametrize(("apps", "ratio"), [((), 0.25), (("Spotify",), 1.0), (("Spotify",), 1.5)])
def test_nothing_to_duck_sends_nothing(echo_shell, tmp_path, on_windows_drive, apps, ratio):
    shell, log = echo_shell
    p = WindowsPlayer(shell, tmp_path, duck_apps=apps, duck_ratio=ratio)
    p.duck()
    p.unduck()
    p.close()
    assert not log.exists() or "duck" not in log.read_text()


def test_audio_off_a_windows_drive_disables_ducking(echo_shell, tmp_path):
    shell, log = echo_shell
    p = WindowsPlayer(shell, tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    p.duck()
    p.close()
    assert not log.exists() or "duck" not in log.read_text()


def test_the_loop_compiles_the_ducker_and_restores_on_start_and_exit(tmp_path, on_windows_drive):
    p = WindowsPlayer("x", tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    script = p._cmd[-1]
    assert "Add-Type -Path 'C:\\\\k\\\\keryx-ducker.cs'" in script
    assert script.count("[KeryxDucker]::Unduck($state)") == 3  # start, command, finally
    assert "@STATE@" not in script and "@SOURCE@" not in script


def test_unduck_after_the_player_died_starts_one_that_restores(
    echo_shell, tmp_path, on_windows_drive
):
    shell, log = echo_shell
    p = WindowsPlayer(shell, tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    p.duck()
    assert p._proc is not None
    p._proc.kill()
    p._proc.wait()
    p.unduck()
    p.close()
    assert log.read_text().splitlines() == ["duck 0.25 Spotify", "unduck", "eof"]


def test_close_kills_a_player_that_will_not_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(player_mod, "CLOSE_GRACE", 0.2)
    script = tmp_path / "stubborn"
    script.write_text("#!/bin/sh\nread -r line; echo ok; trap '' HUP; exec sleep 30\n")
    os.chmod(script, 0o755)
    p = WindowsPlayer(str(script))
    p.stop()  # nothing running yet: no process started
    assert p._send("stop") == "ok"
    proc = p._proc
    assert proc is not None
    p.close()
    assert proc.wait(2) is not None


def test_a_quote_in_the_audio_path_is_escaped(tmp_path, monkeypatch):
    monkeypatch.setattr(player_mod, "windows_path", lambda p: "C:\\Users\\O'Brien\\" + p.name)
    p = WindowsPlayer("x", tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    assert "$state = 'C:\\Users\\O''Brien\\keryx-ducked.txt'" in p._cmd[-1]


def test_a_respawned_player_ducks_again_before_playing(echo_shell, tmp_path, on_windows_drive):
    shell, log = echo_shell
    p = WindowsPlayer(shell, tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    p.duck()
    assert p._proc is not None
    p._proc.kill()
    p._proc.wait()
    p._send("stop")
    p.close()
    lines = log.read_text().splitlines()
    # The killed shell logs nothing more; its successor ducks before the stop.
    assert lines == ["duck 0.25 Spotify", "duck 0.25 Spotify", "stop", "eof"]


def test_ducking_that_cannot_work_is_logged_once(tmp_path, on_windows_drive, caplog):
    script = tmp_path / "nodeck"
    script.write_text('#!/bin/sh\nwhile read -r line; do echo "ok 0 disabled: no csc"; done\n')
    os.chmod(script, 0o755)
    p = WindowsPlayer(str(script), tmp_path, duck_apps=("Spotify",), duck_ratio=0.25)
    with caplog.at_level("WARNING", logger="keryx"):
        p.duck()
        p.duck()
    p.close()
    assert [r.getMessage() for r in caplog.records] == ["could not duck other apps: no csc"]
