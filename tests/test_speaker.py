import threading
import time

import numpy as np
import pytest

from keryx.speaker import Speaker, Utterance


class FakeVoice:
    def synth(self, text):
        return np.zeros(240, dtype=np.float32), 24000


class FakePlayer:
    """Records plays; a play lasts until released or interrupted."""

    def __init__(self, hold=False):
        self.played: list[str] = []
        self.started = threading.Event()
        self.release = threading.Event()
        if not hold:
            self.release.set()

    def play(self, wav, seconds, interrupt):
        self.played.append(wav.name)
        self.started.set()
        while not self.release.is_set():
            if interrupt.wait(0.01):
                return False
        return True

    def stop(self):
        pass


def wait_idle(sp, timeout=3.0):
    deadline = time.time() + timeout
    while not sp.idle():
        if time.time() > deadline:
            raise AssertionError("speaker never went idle")
        time.sleep(0.01)


@pytest.fixture
def make(tmp_path):
    made = []

    def _make(player=None, shorten=lambda t: t):
        sp = Speaker(shorten, FakeVoice(), player or FakePlayer(), tmp_path)
        made.append(sp)
        return sp

    yield _make
    for sp in made:
        sp.stop()
        sp.close()


def test_reply_is_shortened_and_split_into_sentences(make):
    player = FakePlayer()
    sp = make(player, shorten=lambda t: "First. Second.")
    sp.submit(Utterance("a long reply", session="s1"))
    wait_idle(sp)
    assert sp.spoken == ["First.", "Second."]
    assert len(player.played) == 2


def test_notice_is_not_shortened(make):
    sp = make(shorten=lambda t: "WRONG")
    sp.submit(Utterance("I need your permission.", kind="notice"))
    wait_idle(sp)
    assert sp.spoken == ["I need your permission."]


def test_source_announced_only_when_it_changes(make):
    sp = make()
    for src in ["ariadne", "ariadne", "pharos"]:
        sp.submit(Utterance("Done.", source=src))
    wait_idle(sp)
    assert sp.spoken == ["ariadne: Done.", "Done.", "pharos: Done."]


def test_empty_line_is_silent(make):
    player = FakePlayer()
    sp = make(player, shorten=lambda t: "")
    sp.submit(Utterance("```code```"))
    wait_idle(sp)
    assert player.played == []


def test_stop_cuts_playing_and_drops_queued_for_that_session(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("Playing now.", session="a"))
    assert player.started.wait(2)
    sp.submit(Utterance("Queued for a.", session="a"))
    sp.submit(Utterance("Queued for b.", session="b"))
    sp.stop("a")
    player.release.set()
    wait_idle(sp)
    assert "Queued for a." not in sp.spoken
    assert sp.spoken[-1] == "Queued for b."


def test_stop_for_other_session_leaves_speech_alone(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("Keep going.", session="a"))
    assert player.started.wait(2)
    sp.stop("b")
    player.release.set()
    wait_idle(sp)
    assert sp.spoken == ["Keep going."]
    assert len(player.played) == 1


def test_stop_all(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("One.", session="a"))
    assert player.started.wait(2)
    sp.submit(Utterance("Two.", session="b"))
    sp.stop()
    wait_idle(sp)
    assert sp.spoken == ["One."]


def test_wav_slots_rotate(make, tmp_path):
    player = FakePlayer()
    sp = make(player)
    sp.submit(Utterance(" ".join(f"S{i}." for i in range(10))))
    wait_idle(sp)
    assert player.played[:3] == ["keryx-0.wav", "keryx-1.wav", "keryx-2.wav"]
    assert player.played[8] == "keryx-0.wav"


class BrokenVoice:
    def __init__(self):
        self.calls = 0

    def synth(self, text):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("kokoro choked")
        return np.zeros(240, dtype=np.float32), 24000


class FlakyPlayer(FakePlayer):
    def play(self, wav, seconds, interrupt):
        if not self.played:
            self.played.append("boom")
            raise BrokenPipeError("powershell died")
        return super().play(wav, seconds, interrupt)


def test_a_synthesis_error_does_not_silence_later_speech(tmp_path):
    player = FakePlayer()
    sp = Speaker(lambda t: t, BrokenVoice(), player, tmp_path)
    sp.submit(Utterance("First."))
    sp.submit(Utterance("Second."))
    wait_idle(sp)
    assert sp.spoken == ["Second."]
    sp.close()


def test_a_playback_error_does_not_silence_later_speech(tmp_path):
    player = FlakyPlayer()
    sp = Speaker(lambda t: t, FakeVoice(), player, tmp_path)
    sp.submit(Utterance("First."))
    sp.submit(Utterance("Second."))
    wait_idle(sp)
    assert len(player.played) == 2
    sp.close()


def test_stop_cancels_audio_already_queued_behind_another_session(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("B speaks first.", session="b"))
    assert player.started.wait(2)
    sp.submit(Utterance("A is queued.", session="a"))
    deadline = time.time() + 2
    while "A is queued." not in sp.spoken:  # synthesized, waiting for playback
        assert time.time() < deadline
        time.sleep(0.01)
    sp.stop("a")
    player.release.set()
    wait_idle(sp)
    assert len(player.played) == 1


def test_slot_files_carry_a_keryx_prefix(make):
    player = FakePlayer()
    sp = make(player)
    sp.submit(Utterance("One."))
    wait_idle(sp)
    assert player.played == ["keryx-0.wav"]
