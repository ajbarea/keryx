import os
import time

import numpy as np
import pytest
import soundfile as sf
from test_speaker import FakePlayer, FakeVoice, wait_idle

from keryx.replies import GAP, ReplyClips, replies_dir
from keryx.speaker import Speaker, Utterance

S1 = "3f1c0a52-7b1e-4c0e-9a55-2f6f0d1d7a10"
S2 = "9b8d2c0c-509e-42f8-ab6c-af373626b4d5"
RATE = 24000


@pytest.fixture
def klepsydra(tmp_path):
    (tmp_path / "fleet").mkdir()
    return tmp_path


def tone(n, value=0.5):
    return np.full(n, value, dtype=np.float32), RATE


def test_the_folder_sits_beside_the_fleet_folder(tmp_path):
    assert replies_dir(tmp_path / "fleet") == tmp_path / "replies"
    assert replies_dir(None) is None


def test_a_reply_is_one_clip_with_a_gap_between_sentences(klepsydra):
    ReplyClips(replies_dir(klepsydra / "fleet")).save(S1, [tone(2400), tone(1200)])
    samples, rate = sf.read(klepsydra / "replies" / f"{S1}.wav", dtype="float32")
    assert rate == RATE
    assert len(samples) == 2400 + round(RATE * GAP) + 1200
    assert samples[2400 + 10] == 0.0, "silence between the sentences"
    assert samples[0] == pytest.approx(0.5, abs=1e-3)


def test_a_later_reply_replaces_the_sessions_clip(klepsydra):
    clips = ReplyClips(replies_dir(klepsydra / "fleet"))
    clips.save(S1, [tone(2400)])
    clips.save(S1, [tone(480)])
    assert len(sf.read(klepsydra / "replies" / f"{S1}.wav")[0]) == 480
    assert sorted(p.name for p in (klepsydra / "replies").iterdir()) == [f"{S1}.wav"], (
        "no temp file left"
    )


def test_nothing_is_written_without_klepsydra_or_a_session(tmp_path, klepsydra):
    ReplyClips(replies_dir(tmp_path / "missing" / "fleet")).save(S1, [tone(240)])
    assert not (tmp_path / "missing").exists(), "klepsydra not installed: no folder made"
    clips = ReplyClips(replies_dir(klepsydra / "fleet"))
    for session in ("", "not-a-session", "../" + S1, S1.upper()):
        clips.save(session, [tone(240)])
    clips.save(S1, [])
    ReplyClips(replies_dir(klepsydra / "fleet"), enabled=False).save(S1, [tone(240)])
    assert not (klepsydra / "replies").exists()


def test_a_symlinked_fleet_folder_gets_no_clips(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "fleet").symlink_to(tmp_path / "real")
    ReplyClips(replies_dir(tmp_path / "fleet")).save(S1, [tone(240)])
    assert not (tmp_path / "replies").exists()


def test_a_sentence_at_another_rate_is_left_out(klepsydra):
    ReplyClips(replies_dir(klepsydra / "fleet")).save(
        S1, [tone(240), (np.zeros(100, np.float32), 16000)]
    )
    assert len(sf.read(klepsydra / "replies" / f"{S1}.wav")[0]) == 240


def test_only_the_newest_clips_are_kept_and_stale_temp_files_go(klepsydra):
    clips = ReplyClips(replies_dir(klepsydra / "fleet"), keep=2)
    folder = klepsydra / "replies"
    folder.mkdir()
    stale = folder / f"tmp-1-{S2}.wav"
    stale.write_bytes(b"x")
    os.utime(stale, (time.time() - 120, time.time() - 120))
    fresh = folder / f"tmp-2-{S2}.wav"
    fresh.write_bytes(b"x")
    other = folder / "notes.txt"
    other.write_text("not ours")
    sessions = [f"0000000{i}-0000-4000-8000-000000000000" for i in range(4)]
    for i, s in enumerate(sessions):
        clips.save(s, [tone(240)])
        os.utime(folder / f"{s}.wav", (1000 + i, 1000 + i))
    clips.save(S1, [tone(240)])
    left = sorted(p.name for p in folder.iterdir())
    assert left == sorted([f"{S1}.wav", f"{sessions[3]}.wav", fresh.name, "notes.txt"])


def test_a_write_failure_is_swallowed(klepsydra, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("keryx.replies.write_wav", broken)
    ReplyClips(replies_dir(klepsydra / "fleet")).save(S1, [tone(240)])
    assert list((klepsydra / "replies").iterdir()) == []


class Recorder(ReplyClips):
    def __init__(self):
        super().__init__(None)
        self.saved: list[tuple[str, int]] = []

    def save(self, session, sentences):
        self.saved.append((session, len(sentences)))


@pytest.fixture
def speaker(tmp_path):
    made = []

    def _make(shorten=lambda t: t, player=None):
        rec = Recorder()
        sp = Speaker(shorten, FakeVoice(), player or FakePlayer(), tmp_path, replies=rec)
        made.append(sp)
        return sp, rec

    yield _make
    for sp in made:
        sp.stop()
        sp.close()


def test_the_speaker_keeps_a_whole_reply_without_its_repo_name(speaker):
    sp, rec = speaker(shorten=lambda t: "First. Second.")
    sp.submit(Utterance("a long reply", session=S1, source="klepsydra"))
    wait_idle(sp)
    assert rec.saved == [(S1, 2)], "two sentences, the announcement left out"


def test_a_notice_or_a_replay_is_not_kept(speaker):
    sp, rec = speaker()
    sp.submit(Utterance("Needs your approval.", kind="notice", session=S1))
    wait_idle(sp)
    sp.submit(Utterance("Done.", session=S1))
    wait_idle(sp)
    assert sp.again(S1)
    wait_idle(sp)
    assert rec.saved == [(S1, 1)]


def test_a_reply_cut_off_while_it_is_synthesized_keeps_the_last_clip(speaker):
    player = FakePlayer(hold=True)
    sp, rec = speaker(shorten=lambda t: "One. Two. Three. Four. Five.", player=player)
    sp.submit(Utterance("reply", session=S1))
    assert player.started.wait(2)
    sp.stop(S1)
    player.release.set()
    wait_idle(sp)
    assert rec.saved == []
