import threading
import time

import numpy as np
import pytest

from keryx.speaker import Speaker, Utterance
from keryx.voices import VoiceSpec


class FakeVoice:
    def __init__(self):
        self.voices = []

    def synth(self, text, voice=None):
        self.voices.append(voice)
        return np.zeros(240, dtype=np.float32), 24000

    def has(self, spec):
        return True


class FakePlayer:
    """Records plays; a play lasts until released or interrupted."""

    def __init__(self, hold=False):
        self.played: list[str] = []
        self.events: list[str] = []  # duck and unduck, in order
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

    def duck(self):
        self.events.append("duck")

    def unduck(self):
        self.events.append("unduck")


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
    assert list(sp.spoken) == ["First.", "Second."]
    assert len(player.played) == 2


def test_notice_is_not_shortened(make):
    sp = make(shorten=lambda t: "WRONG")
    sp.submit(Utterance("I need your permission.", kind="notice"))
    wait_idle(sp)
    assert list(sp.spoken) == ["I need your permission."]


def test_source_announced_only_when_it_changes(make):
    sp = make()
    for src in ["ariadne", "ariadne", "pharos"]:
        sp.submit(Utterance("Done.", source=src))
    wait_idle(sp)
    assert list(sp.spoken) == ["ariadne:", "Done.", "Done.", "pharos:", "Done."]


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
    assert list(sp.spoken) == ["Keep going."]
    assert len(player.played) == 1


def test_stop_all(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("One.", session="a"))
    assert player.started.wait(2)
    sp.submit(Utterance("Two.", session="b"))
    sp.stop()
    wait_idle(sp)
    assert list(sp.spoken) == ["One."]


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

    def synth(self, text, voice=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("kokoro choked")
        return np.zeros(240, dtype=np.float32), 24000

    def has(self, spec):
        return True


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
    assert list(sp.spoken) == ["Second."]
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


def test_a_cancelled_announcement_is_repeated_next_time(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("First.", session="x", source="other"))
    assert player.started.wait(2)
    sp.submit(Utterance("Never heard.", session="a", source="ariadne"))
    wait_for(lambda: sp._play_q.full() and not sp._pending)  # it is synthesizing, blocked
    sp.stop("a")
    player.release.set()
    wait_idle(sp)
    sp.submit(Utterance("Heard.", session="a", source="ariadne"))
    wait_idle(sp)
    assert list(sp.spoken)[-2:] == ["ariadne:", "Heard."]


def test_a_notice_is_spoken_while_a_reply_waits_on_the_summarizer(make):
    loaded = threading.Event()

    def slow_shorten(text):
        loaded.wait(5)
        return "The reply."

    sp = make(shorten=slow_shorten)
    sp.submit(Utterance("a long reply", session="a"))
    sp.submit(Utterance("I need your permission.", kind="notice", session="b"))
    deadline = time.time() + 2
    while "I need your permission." not in sp.spoken:
        assert time.time() < deadline
        time.sleep(0.01)
    loaded.set()
    wait_idle(sp)
    assert list(sp.spoken) == ["I need your permission.", "The reply."]


def test_a_reply_cancelled_while_shortening_is_never_spoken(make):
    started, loaded = threading.Event(), threading.Event()

    def slow_shorten(text):
        started.set()
        loaded.wait(5)
        return text

    sp = make(shorten=slow_shorten)
    sp.submit(Utterance("Stale.", session="a"))
    assert started.wait(2)
    sp.submit(Utterance("Also stale.", session="a"))
    sp.stop("a")
    loaded.set()
    wait_idle(sp)
    sp.submit(Utterance("Fresh.", session="a"))
    wait_idle(sp)
    assert list(sp.spoken) == ["Fresh."]


def test_a_shortening_error_does_not_silence_later_speech(make):
    calls = []

    def flaky(text):
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError("ollama choked")
        return text

    sp = make(shorten=flaky)
    sp.submit(Utterance("First."))
    sp.submit(Utterance("Second."))
    wait_idle(sp)
    assert list(sp.spoken) == ["Second."]


class FakeVoices:
    def __init__(self, picked):
        self.picked = picked
        self.claimed = []

    def assign(self, holder, source):
        self.claimed.append((holder, source))
        return self.picked.get(holder)


def test_each_utterance_is_spoken_in_the_voice_picked_for_its_session(tmp_path):
    voice = FakeVoice()
    picked = {"a": VoiceSpec(("af_heart",)), "b": VoiceSpec(("bm_george",))}
    sp = Speaker(lambda t: t, voice, FakePlayer(), tmp_path, FakeVoices(picked))
    sp.submit(Utterance("One.", kind="notice", session="a"))
    wait_idle(sp)
    sp.submit(Utterance("Two.", kind="notice", session="b"))
    wait_idle(sp)
    assert voice.voices == [picked["a"], picked["b"]]
    sp.close()


def test_an_explicit_voice_is_kept(tmp_path):
    voice = FakeVoice()
    chosen = VoiceSpec(("bf_emma",))
    sp = Speaker(lambda t: t, voice, FakePlayer(), tmp_path, FakeVoices({}))
    sp.submit(Utterance("Hi.", kind="notice", voice=chosen))
    wait_idle(sp)
    assert voice.voices == [chosen]
    sp.close()


def test_claim_reaches_the_voices(tmp_path):
    voices = FakeVoices({})
    sp = Speaker(lambda t: t, FakeVoice(), FakePlayer(), tmp_path, voices)
    sp.claim("a", "repo")
    sp.claim("", "repo")  # no holder: nothing to hold
    assert voices.claimed == [("a", "repo")]
    sp.close()


def test_the_terminal_holds_the_voice_when_there_is_one(tmp_path):
    voices = FakeVoices({"9:1": VoiceSpec(("bm_george",)), "s": VoiceSpec(("af_heart",))})
    sp = Speaker(lambda t: t, FakeVoice(), FakePlayer(), tmp_path, voices)
    sp.submit(Utterance("Hi.", kind="notice", session="s", terminal="9:1"))
    sp.submit(Utterance("Hi.", kind="notice", session="s"))
    wait_idle(sp)
    assert voices.claimed == [("9:1", ""), ("s", "")]
    sp.close()


@pytest.fixture
def quick_unduck(monkeypatch):
    from keryx import speaker as speaker_mod

    monkeypatch.setattr(speaker_mod, "UNDUCK_AFTER", 0.05)


def wait_for(cond, timeout=3.0):
    deadline = time.time() + timeout
    while not cond():
        assert time.time() < deadline
        time.sleep(0.01)


def test_other_apps_duck_once_for_a_run_of_lines_then_come_back(make, quick_unduck):
    player = FakePlayer()
    sp = make(player)
    sp.submit(Utterance("One. Two. Three.", kind="notice"))
    sp.submit(Utterance("Four.", kind="notice"))
    wait_idle(sp)
    wait_for(lambda: player.events[-1:] == ["unduck"])
    assert player.events == ["duck", "unduck"]
    assert len(player.played) == 4


def test_ducking_starts_only_when_audio_plays(make, quick_unduck):
    player = FakePlayer()
    sp = make(player, shorten=lambda t: "")
    sp.submit(Utterance("```code```"))  # nothing to say
    wait_idle(sp)
    time.sleep(0.2)
    assert player.events == []


def test_a_reply_waiting_on_the_summarizer_does_not_hold_the_music_down(make, quick_unduck):
    player = FakePlayer()
    loaded = threading.Event()

    def slow(text):
        loaded.wait(5)
        return "Later."

    sp = make(player, shorten=slow)
    sp.submit(Utterance("Now.", kind="notice"))
    sp.submit(Utterance("a long reply"))
    wait_for(lambda: player.events == ["duck", "unduck"])  # back up while the model loads
    loaded.set()
    wait_idle(sp)
    wait_for(lambda: player.events == ["duck", "unduck", "duck", "unduck"])


def test_stopping_speech_brings_the_music_back(make, quick_unduck):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("Long line.", session="a"))
    assert player.started.wait(2)
    sp.stop("a")
    wait_idle(sp)
    wait_for(lambda: player.events == ["duck", "unduck"])


def test_a_ducking_error_does_not_silence_speech(tmp_path, quick_unduck):
    class BrokenDuck(FakePlayer):
        def duck(self):
            raise OSError("powershell died")

    player = BrokenDuck()
    sp = Speaker(lambda t: t, FakeVoice(), player, tmp_path)
    sp.submit(Utterance("Still heard.", kind="notice"))
    wait_idle(sp)
    assert len(player.played) == 1
    sp.close()


def test_closing_while_ducked_brings_the_music_back(tmp_path):
    player = FakePlayer()
    sp = Speaker(lambda t: t, FakeVoice(), player, tmp_path)
    sp.submit(Utterance("Hi.", kind="notice"))
    wait_idle(sp)
    sp.close()
    assert player.events == ["duck", "unduck"]


def test_again_says_a_holders_last_line_in_the_same_voice(tmp_path):
    voice = FakeVoice()
    picked = {"9:1": VoiceSpec(("bm_george",)), "8:1": VoiceSpec(("af_heart",))}
    sp = Speaker(lambda t: "The gist.", voice, FakePlayer(), tmp_path, FakeVoices(picked))
    sp.submit(Utterance("a long reply", session="s", terminal="9:1"))
    sp.submit(Utterance("Other.", kind="notice", session="t", terminal="8:1"))
    wait_idle(sp)
    assert sp.again("9:1") is True
    wait_idle(sp)
    assert list(sp.spoken)[-1] == "The gist."
    assert voice.voices[-1] == picked["9:1"]
    sp.close()


def test_again_with_nothing_said_yet_reports_it(make):
    sp = make()
    assert sp.again("9:1") is False
    assert sp.again("") is False


def test_again_without_a_holder_says_the_latest_line(make):
    sp = make()
    sp.submit(Utterance("First.", kind="notice", session="a"))
    wait_idle(sp)
    sp.submit(Utterance("Second.", kind="notice", session="b"))
    wait_idle(sp)
    assert sp.again("") is True
    wait_idle(sp)
    assert list(sp.spoken)[-1] == "Second."


def test_again_keeps_the_repo_announcement(make):
    sp = make()
    sp.submit(Utterance("Done.", kind="notice", session="a", source="ariadne"))
    wait_idle(sp)
    sp.again("a")
    wait_idle(sp)
    assert list(sp.spoken)[-4:] == ["ariadne:", "Done.", "ariadne:", "Done."]


def test_pronunciations_change_what_is_synthesized_not_what_is_logged(tmp_path):
    said = []

    class Ears(FakeVoice):
        def synth(self, text, voice=None):
            said.append(text)
            return super().synth(text, voice)

    sp = Speaker(lambda t: t, Ears(), FakePlayer(), tmp_path, pronounce=str.upper)
    sp.submit(Utterance("ajsoftworks is done.", kind="notice"))
    wait_idle(sp)
    assert said == ["AJSOFTWORKS IS DONE."]
    assert list(sp.spoken) == ["ajsoftworks is done."]
    sp.close()


def test_again_cuts_off_the_line_it_repeats(tmp_path):
    player = FakePlayer(hold=True)
    sp = Speaker(lambda t: t, FakeVoice(), player, tmp_path)
    sp.submit(Utterance("One. Two. Three.", kind="notice", session="s"))
    assert player.started.wait(2)
    assert sp.again("s") is True
    player.release.set()
    wait_idle(sp)
    # "One." was cut off, then the whole line played again; "Two." and "Three." never twice.
    assert player.played.count("keryx-0.wav") == 1
    assert list(sp.spoken)[-3:] == ["One.", "Two.", "Three."]


def test_again_keeps_a_new_reply_still_with_the_summarizer(tmp_path):
    loaded = threading.Event()

    def slow(text):
        loaded.wait(5)
        return "New gist."

    sp = Speaker(slow, FakeVoice(), FakePlayer(), tmp_path)
    sp.submit(Utterance("Old line.", kind="notice", session="s"))
    wait_idle(sp)
    sp.submit(Utterance("a new reply", session="s"))
    assert sp.again("s") is True
    loaded.set()
    wait_idle(sp)
    assert list(sp.spoken)[-2:] == ["Old line.", "New gist."]
    sp.close()


def test_the_name_is_announced_when_the_line_before_it_was_cut_off_unheard(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("X.", session="a", source="ariadne"))
    assert player.started.wait(2)
    sp.submit(Utterance("Y.", session="b", source="ariadne"))
    wait_for(lambda: sp._play_q.full() and not sp._pending)  # Y is synthesizing, blocked
    sp.stop("a")
    player.release.set()
    wait_idle(sp)
    assert list(sp.spoken)[-2:] == ["ariadne:", "Y."]


def test_again_keeps_a_reply_waiting_behind_the_line_being_said(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("One. Two. Three. Four. Five.", kind="notice", session="s"))
    assert player.started.wait(2)
    sp.submit(Utterance("Later.", kind="notice", session="s"))
    wait_for(lambda: len(sp._pending) == 1)  # shortened, not yet synthesizing
    assert sp.again("s") is True
    player.release.set()
    wait_idle(sp)
    assert "Later." in sp.spoken
    assert list(sp.spoken)[-6:] == ["Later.", "One.", "Two.", "Three.", "Four.", "Five."]


def test_a_line_not_yet_playing_cannot_be_said_again(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("Heard.", kind="notice", session="a"))
    assert player.started.wait(2)
    sp.submit(Utterance("Not yet.", kind="notice", session="b"))
    wait_for(lambda: "Not yet." in sp.spoken)  # synthesized, queued behind the first
    assert sp.again("b") is False
    player.release.set()
    wait_idle(sp)
    assert sp.again("b") is True


def test_a_replayed_line_is_announced_even_when_its_name_was_just_heard(make):
    sp = make()
    sp.submit(Utterance("Done.", kind="notice", session="a", source="ariadne"))
    wait_idle(sp)
    sp.submit(Utterance("More.", kind="notice", session="b", source="ariadne"))
    wait_idle(sp)
    sp.again("a")
    wait_idle(sp)
    assert list(sp.spoken)[-2:] == ["ariadne:", "Done."]


def test_stop_reaches_what_a_terminal_left_speaking_under_an_old_session(make):
    player = FakePlayer(hold=True)
    sp = make(player)
    sp.submit(Utterance("Old.", session="old", terminal="9:1"))
    assert player.started.wait(2)
    sp.submit(Utterance("Elsewhere.", session="other", terminal="8:1"))
    wait_for(lambda: "Elsewhere." in sp.spoken)
    sp.stop("new", "9:1")  # /clear: the terminal's new session sends the next prompt
    player.release.set()
    wait_idle(sp)
    assert player.played == ["keryx-0.wav", "keryx-1.wav"]  # Old. was cut; Elsewhere. played
