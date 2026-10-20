import json
import math
import os
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from keryx import speaking
from keryx.speaker import Speaker, Utterance
from keryx.speaking import SpeakingSignal, claude_of, envelope, fleet_dir

RATE = 24000


def sine(seconds, amp=0.5, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * math.pi * 440 * t)).astype(np.float32)


def test_envelope_silence_is_zeros_with_ceil_length():
    env = envelope(np.zeros(int(RATE * 1.01), dtype=np.float32), RATE)
    assert env == [0.0] * math.ceil(1.01 * 20)


def test_envelope_sine_is_flat_and_full_scale():
    env = envelope(sine(2.0), RATE)
    assert len(env) == 40
    assert set(env) == {1.0}


def test_envelope_length_and_two_decimals_for_a_ragged_clip():
    samples = np.concatenate([sine(0.5, 0.1), sine(0.33, 0.4)])
    env = envelope(samples, RATE)
    assert len(env) == math.ceil(len(samples) / RATE * 20)
    assert max(env) == 1.0 and 0.2 < env[0] < 0.3
    assert all(round(v, 2) == v for v in env)


def test_envelope_empty_clip():
    assert envelope(np.zeros(0, dtype=np.float32), RATE) == []


def test_claude_of_terminal_key():
    assert claude_of("1234:987654") == (1234, 987654)
    assert claude_of("") is None
    assert claude_of("tty3") is None
    assert claude_of("12:x") is None


def test_fleet_dir_mirrors_the_hook():
    assert fleet_dir({"KLEPSYDRA_DIR": "/k"}) == Path("/k/fleet")
    wsl = fleet_dir({"USER": "aj"}, osrelease="5.15-microsoft-standard-WSL2")
    assert wsl == Path("/mnt/c/Users/aj/AppData/Local/dev.ajsoftworks.klepsydra/fleet")
    assert fleet_dir({"HOME": "/h"}, osrelease="6.1") == Path(
        "/h/.local/share/dev.ajsoftworks.klepsydra/fleet"
    )
    assert fleet_dir({"HOME": "/h", "XDG_DATA_HOME": "rel"}, osrelease="6.1") == Path(
        "/h/.local/share/dev.ajsoftworks.klepsydra/fleet"
    )
    assert fleet_dir({"XDG_DATA_HOME": "/x"}, osrelease="6.1") == Path(
        "/x/dev.ajsoftworks.klepsydra/fleet"
    )
    assert fleet_dir({}, osrelease="5-microsoft") is None


def make(tmp_path, **kw):
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    return SpeakingSignal(
        fleet, clock=lambda: 100.0, background=False, **kw
    ), fleet / "speaking.json"


def test_atomic_write_fields_and_no_litter(tmp_path):
    sig, path = make(tmp_path)
    sig.start("a", 1.5, [0.5, 1.0], "af_heart", "4242:777", "sess")
    assert json.loads(path.read_text()) == {
        "v": 1,
        "voice": "af_heart",
        "terminal": "4242:777",
        "claude_pid": 4242,
        "claude_start": 777,
        "session_id": "sess",
        "started_at": 100.0,
        "ends_at": 101.5,
        "envelope": [0.5, 1.0],
    }
    assert [p.name for p in path.parent.iterdir()] == ["speaking.json"]


def test_write_goes_through_a_temp_file_and_rename(tmp_path, monkeypatch):
    sig, path = make(tmp_path)
    calls = []
    real = os.replace
    monkeypatch.setattr(speaking.os, "replace", lambda a, b: (calls.append((a, b)), real(a, b)))
    sig.start("a", 1, [], "v", "", "")
    ((src, dst),) = calls
    assert dst == path and src.parent == path.parent and src != path


def test_no_pid_fields_without_a_claude_terminal(tmp_path):
    sig, path = make(tmp_path)
    sig.start("a", 1, [], "v", "", "")
    doc = json.loads(path.read_text())
    assert "claude_pid" not in doc and "claude_start" not in doc and "session_id" not in doc


def test_absent_folder_writes_nothing(tmp_path):
    sig = SpeakingSignal(tmp_path / "nope", background=False)
    sig.start("a", 1, [], "v", "", "")
    sig.clear()
    assert not (tmp_path / "nope").exists()
    SpeakingSignal(None).start("a", 1, [], "v", "", "")


def test_disabled_writes_nothing(tmp_path):
    sig, path = make(tmp_path, enabled=False)
    sig.start("a", 1, [], "v", "", "")
    assert not path.exists()


def test_a_new_line_replaces_the_file(tmp_path):
    sig, path = make(tmp_path)
    sig.start("a", 1, [1.0], "one", "", "")
    sig.start("b", 2, [0.3], "two", "", "")
    assert json.loads(path.read_text())["voice"] == "two"


def test_clear_removes_and_only_the_owner_can_clear_by_owner(tmp_path):
    sig, path = make(tmp_path)
    sig.start("a", 1, [], "v", "", "")
    sig.clear("b")
    assert path.exists()
    sig.clear("a")
    assert not path.exists()
    sig.start("a", 1, [], "v", "", "")
    sig.clear()
    assert not path.exists()
    sig.clear()  # already gone


def test_write_error_is_swallowed_and_leaves_no_temp(tmp_path, monkeypatch):
    sig, path = make(tmp_path)
    monkeypatch.setattr(speaking.os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("x")))
    sig.start("a", 1, [], "v", "", "")
    assert list(path.parent.iterdir()) == []


def test_unwritable_target_is_swallowed(tmp_path, monkeypatch):
    sig, _ = make(tmp_path)
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    sig.start("a", 1, [], "v", "", "")
    monkeypatch.setattr(Path, "unlink", lambda *a, **k: (_ for _ in ()).throw(OSError("ro")))
    sig.clear()


# --- through the speaker ---


class Voice:
    def synth(self, text, voice=None):
        return sine(0.3), RATE

    def has(self, spec):
        return True


class Player:
    def __init__(self):
        self.release = threading.Event()
        self.started = threading.Event()

    def play(self, wav, seconds, interrupt):
        self.started.set()
        while not self.release.is_set():
            if interrupt.wait(0.01):
                return False
        return True

    def stop(self): ...
    def duck(self): ...
    def unduck(self): ...


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while not cond():
        assert time.time() < end, "timed out"
        time.sleep(0.01)


def test_speaker_writes_on_play_and_clears_on_stop(tmp_path):
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    path = fleet / "speaking.json"
    player = Player()
    sp = Speaker(lambda t: t, Voice(), player, tmp_path, signal=SpeakingSignal(fleet))
    try:
        sp.submit(Utterance("Hello there.", kind="notice", session="s", terminal="9:8"))
        wait_for(path.exists)
        doc = json.loads(path.read_text())
        assert doc["claude_pid"] == 9 and doc["session_id"] == "s"
        assert doc["ends_at"] - doc["started_at"] == pytest.approx(0.3)
        assert len(doc["envelope"]) == 6
        sp.stop()
        wait_for(lambda: not path.exists())
    finally:
        player.release.set()
        sp.close()


def test_a_second_line_replaces_the_first_and_quiet_clears(tmp_path):
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    path = fleet / "speaking.json"
    player = Player()
    player.release.set()
    sp = Speaker(lambda t: t, Voice(), player, tmp_path, signal=SpeakingSignal(fleet))
    try:
        sp.submit(Utterance("One.", kind="notice", session="a"))
        wait_for(path.exists)
        sp.submit(Utterance("Two.", kind="notice", session="b"))
        wait_for(lambda: path.exists() and json.loads(path.read_text())["session_id"] == "b")
    finally:
        sp.close()
    assert not path.exists()  # close clears


def test_background_writes_keep_order_and_close_flushes(tmp_path):
    fleet = tmp_path / "fleet"
    fleet.mkdir()
    sig = SpeakingSignal(fleet)
    for i in range(20):
        sig.start(i, 1, [], f"v{i}", "", "")
    sig.close()
    assert json.loads((fleet / "speaking.json").read_text())["voice"] == "v19"
    sig.clear()  # after close: runs inline
    assert not (fleet / "speaking.json").exists()
