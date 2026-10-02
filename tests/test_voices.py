import pytest

from keryx.voices import POOL, VoiceBook, VoiceSpec, catalogue, pool


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def book(tmp_path):
    clock = Clock()
    return VoiceBook(tmp_path / "voices.json", clock=clock, active_seconds=60), clock


def test_the_first_session_gets_the_configured_voice(book):
    b, _ = book
    assert b.assign("s1", "ariadne") == VoiceSpec(("af_heart",))


def test_sessions_in_different_repos_sound_different(book):
    b, _ = book
    voices = {b.assign(f"s{i}", f"repo{i}") for i in range(len(POOL))}
    assert len(voices) == len(POOL)


def test_two_sessions_in_one_repo_sound_different(book):
    b, _ = book
    assert b.assign("s1", "ariadne") != b.assign("s2", "ariadne")


def test_a_session_keeps_its_voice(book):
    b, _ = book
    first = b.assign("s1", "ariadne")
    b.assign("s2", "pharos")
    assert b.assign("s1", "ariadne") == first


def test_a_repo_keeps_its_voice_across_sessions_and_restarts(tmp_path):
    clock = Clock()
    b = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60)
    b.assign("s1", "ariadne")
    pharos = b.assign("s2", "pharos")
    clock.now = 61  # both sessions have ended
    again = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60)
    assert again.assign("new-session", "pharos") == pharos


def test_a_silent_session_releases_its_voice(book):
    b, clock = book
    home = b.assign("s1", "ariadne")
    assert b.assign("s2", "ariadne") != home
    clock.now = 61
    b.assign("s3", "pharos")  # s1 and s2 have gone quiet
    assert b.assign("s4", "ariadne") == home


def test_a_borrowed_voice_does_not_change_the_repos_home(tmp_path):
    clock = Clock()
    b = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60)
    home = b.assign("s1", "ariadne")
    b.assign("s2", "ariadne")
    clock.now = 61
    assert b.assign("s3", "ariadne") == home


def test_a_new_repo_avoids_other_repos_voices_even_when_they_are_idle(book):
    b, clock = book
    homes = {b.assign(f"s{i}", f"repo{i}") for i in range(3)}
    clock.now = 61
    assert b.assign("late", "newrepo") not in homes


def test_more_sessions_than_stock_voices_get_blends_not_repeats(book):
    b, _ = book
    voices = [b.assign(f"s{i}", f"repo{i}") for i in range(len(POOL) + 5)]
    assert len(set(voices)) == len(voices)
    assert all(len(v.names) == 2 for v in voices[len(POOL) :])


def test_every_voice_taken_still_answers(tmp_path):
    b = VoiceBook(tmp_path / "v.json", clock=Clock(), active_seconds=60)
    for i in range(len(catalogue(POOL[0])) + 3):
        assert isinstance(b.assign(f"s{i}", ""), VoiceSpec)


def test_no_session_gets_the_default(book):
    b, _ = book
    b.assign("s1", "ariadne")
    assert b.assign("", "") == b.default()


def test_a_configured_voice_leads_the_pool():
    assert pool("bm_george")[0] == "bm_george"
    assert pool("bm_george").count("bm_george") == 1
    assert pool("am_santa")[:2] == ("am_santa", "af_heart")


def test_blends_pair_only_same_gender_voices():
    for spec in catalogue(POOL[0]):
        if len(spec.names) == 2:
            assert spec.names[0][1] == spec.names[1][1]


def test_labels_are_unique_and_round_trip():
    specs = catalogue(POOL[0])
    assert len({s.label() for s in specs}) == len(specs)
    for spec in specs:
        assert VoiceSpec.parse(spec.label()) == spec


def test_british_voices_use_british_phonemes():
    assert VoiceSpec(("bf_emma",)).lang == "en-gb"
    assert VoiceSpec(("af_heart",)).lang == "en-us"


def test_a_corrupt_file_starts_empty(tmp_path):
    (tmp_path / "v.json").write_text("{nope")
    b = VoiceBook(tmp_path / "v.json")
    assert b.assign("s1", "ariadne") == b.default()


def test_a_label_no_longer_in_the_catalogue_is_forgotten(tmp_path):
    (tmp_path / "v.json").write_text('{"homes": {"ariadne": {"voice": "zz_gone", "seen": 1}}}')
    b = VoiceBook(tmp_path / "v.json")
    assert b.assign("s1", "ariadne") == b.default()


@pytest.mark.parametrize(
    "content",
    [
        b"[]",
        b'{"homes": [1]}',
        b'{"homes": {"a": [1]}}',
        b'{"homes": {"a": {"voice": 5}}}',
        b"\xff\xfe",
    ],
)
def test_a_malformed_file_is_ignored(tmp_path, content):
    (tmp_path / "v.json").write_bytes(content)
    b = VoiceBook(tmp_path / "v.json")
    assert b.assign("s1", "ariadne") == b.default()


def test_an_unreadable_file_is_ignored(tmp_path):
    (tmp_path / "v.json").mkdir()  # reading a directory raises OSError
    assert VoiceBook(tmp_path / "v.json").assign("s1", "ariadne") == VoiceSpec(("af_heart",))


def test_holds_survive_a_daemon_restart(tmp_path):
    clock = Clock()
    path = tmp_path / "v.json"
    b = VoiceBook(path, clock=clock, active_seconds=60)
    home = b.assign("a", "repo")
    borrowed = b.assign("b", "repo")
    restarted = VoiceBook(path, clock=clock, active_seconds=60)
    assert restarted.assign("b", "repo") == borrowed  # b speaks first after the restart
    assert restarted.assign("a", "repo") == home


def test_a_prompt_keeps_a_long_turn_holding_its_voice(book):
    b, clock = book
    home = b.assign("a", "repo")
    clock.now = 50
    b.touch("a")
    clock.now = 100  # 50 s after the prompt, 100 s after it last spoke
    b.assign("c", "repo")
    assert b.assign("a", "repo") == home


def test_touch_does_not_revive_an_expired_hold(book):
    b, clock = book
    home = b.assign("a", "repo")
    clock.now = 61
    b.touch("a")
    assert b.assign("c", "repo") == home  # a no longer holds it


def test_repos_unheard_for_long_free_their_voices_for_new_repos(tmp_path):
    clock = Clock()
    b = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60, home_seconds=1000)
    first = b.assign("a", "old-repo")
    clock.now = 1001
    assert b.assign("n", "new-repo") == first


def test_a_repo_that_keeps_speaking_keeps_its_home_reserved(tmp_path):
    clock = Clock()
    b = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60, home_seconds=1000)
    first = b.assign("a", "busy-repo")
    clock.now = 900
    b.assign("a2", "busy-repo")
    clock.now = 1500
    assert b.assign("n", "new-repo") != first


def test_the_file_never_holds_a_partial_write(tmp_path):
    b = VoiceBook(tmp_path / "v.json")
    b.assign("s1", "ariadne")
    assert not (tmp_path / "v.tmp").exists()
    assert "ariadne" in (tmp_path / "v.json").read_text()


@pytest.mark.parametrize(
    ("names", "weights"),
    [
        (("a", "b"), (1.0,)),
        (("a",), (0.0,)),
        (("a", "b"), (0.5, -0.5)),
        ((), ()),
        (("a",), (float("nan"),)),
    ],
)
def test_invalid_specs_are_rejected(names, weights):
    with pytest.raises(ValueError):
        VoiceSpec(names, weights)


def test_a_non_english_first_voice_is_never_blended():
    specs = catalogue("jf_alpha")
    assert specs[0] == VoiceSpec(("jf_alpha",))
    assert not any("jf_alpha" in s.names for s in specs[1:])
