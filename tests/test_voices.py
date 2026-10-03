import numpy as np
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


def test_no_session_with_nobody_holding_gets_the_default(book):
    b, _ = book
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


def test_a_blend_speaks_with_its_heaviest_voices_accent():
    assert VoiceSpec(("af_heart", "bf_emma"), (0.3, 0.7)).lang == "en-gb"
    assert VoiceSpec(("af_heart", "bf_emma"), (0.7, 0.3)).lang == "en-us"


def test_spoken_names_are_readable():
    assert VoiceSpec(("af_heart",)).spoken() == "heart"
    assert VoiceSpec(("af_heart", "bf_emma"), (0.5, 0.5)).spoken() == "heart and emma"


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
    b.assign("a", "repo")  # the prompt claims it again
    clock.now = 100  # 50 s after the prompt, 100 s after it last spoke
    b.assign("c", "repo")
    assert b.assign("a", "repo") == home


def test_a_prompt_after_the_hold_expired_reclaims_the_home_voice(book):
    b, clock = book
    home = b.assign("a", "repo")
    clock.now = 61
    b.assign("a", "repo")  # prompt after a long pause, before anyone else speaks
    assert b.assign("c", "repo") != home
    assert b.assign("a", "repo") == home


def test_a_closed_terminal_frees_its_voice_at_once(tmp_path):
    running = {"1:1": True, "2:1": True}
    b = VoiceBook(tmp_path / "v.json", clock=Clock(), alive=lambda h: running.get(h))
    home = b.assign("1:1", "repo")
    assert b.assign("2:1", "repo") != home
    running["1:1"] = False  # that terminal was closed, or killed
    assert b.assign("3:1", "repo") == home


def test_an_open_terminal_keeps_its_voice_however_long_it_idles(tmp_path):
    clock = Clock()
    b = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60, alive=lambda h: True)
    home = b.assign("1:1", "repo")
    clock.now = 10**6
    assert b.assign("2:1", "repo") != home
    assert b.assign("1:1", "repo") == home


def test_a_new_session_in_the_same_terminal_keeps_its_voice(tmp_path):
    b = VoiceBook(tmp_path / "v.json", clock=Clock(), alive=lambda h: True)
    first = b.assign("1:1", "repo")  # holder is the terminal, so /clear changes nothing
    b.assign("2:1", "repo")
    assert b.assign("1:1", "repo") == first


def test_a_closed_terminal_found_after_a_restart_is_dropped(tmp_path):
    running = {"1:1": True}
    path = tmp_path / "v.json"
    VoiceBook(path, clock=Clock(), alive=lambda h: running.get(h)).assign("1:1", "repo")
    running["1:1"] = False
    again = VoiceBook(path, clock=Clock(), alive=lambda h: running.get(h))
    assert again.assign("2:1", "repo") == VoiceSpec(("af_heart",))


def test_a_notice_without_a_session_avoids_held_voices(book):
    b, _ = book
    held = b.assign("a", "repo")
    assert b.assign("", "") != held
    assert b.assign("c", "other") != held  # and holding nothing, it took nobody's voice


def test_a_clock_that_jumped_back_does_not_hold_voices_forever(book):
    b, clock = book
    clock.now = 1000
    b.assign("a", "repo")
    clock.now = 10  # the host slept and WSL's clock came back early
    b.assign("x", "other")
    clock.now = 71  # 61 s after the jump
    assert b.assign("c", "repo") == VoiceSpec(("af_heart",))


def test_non_finite_times_in_the_file_are_dropped(tmp_path):
    (tmp_path / "v.json").write_text('{"sessions": {"a": {"voice": "af_heart", "seen": Infinity}}}')
    b = VoiceBook(tmp_path / "v.json")
    assert b.assign("c", "repo") == VoiceSpec(("af_heart",))


def test_repos_unheard_for_ninety_days_are_forgotten(tmp_path):
    from keryx.voices import FORGET_SECONDS

    clock = Clock()
    b = VoiceBook(tmp_path / "v.json", clock=clock, active_seconds=60)
    b.assign("a", "old")
    clock.now = FORGET_SECONDS + 1
    b.assign("n", "new")
    assert '"old"' not in (tmp_path / "v.json").read_text()


def test_refreshed_timestamps_are_not_saved_on_every_line(tmp_path):
    clock = Clock()
    path = tmp_path / "v.json"
    b = VoiceBook(path, clock=clock, active_seconds=600)
    b.assign("a", "repo")
    first = path.read_text()
    clock.now = 10
    b.assign("a", "repo")
    assert path.read_text() == first  # only a timestamp moved
    b.assign("b", "repo")
    assert '"b"' in path.read_text()  # a new hold is saved at once


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


class FakeKokoro:
    def __init__(self):
        self.voices = {
            "a": np.full((4, 1, 2), 1.0, np.float32),
            "b": np.full((4, 1, 2), 3.0, np.float32),
        }

    def get_voice_style(self, name):
        return self.voices[name]


def kokoro_voice():
    from keryx.voice import KokoroVoice

    v = object.__new__(KokoroVoice)  # skip loading the real model
    v._kokoro, v._styles = FakeKokoro(), {}
    return v


def test_a_blend_is_the_weighted_mean_of_its_voices():
    style = kokoro_voice().style(VoiceSpec(("a", "b"), (0.75, 0.25)))
    assert np.allclose(style, 1.5)


def test_huge_weights_still_blend_to_finite_styles():
    style = kokoro_voice().style(VoiceSpec(("a", "b"), (1e308, 1e308)))
    assert np.isfinite(style).all() and np.allclose(style, 2.0)


def test_the_style_cache_is_bounded():
    from keryx.voice import STYLE_CACHE

    v = kokoro_voice()
    for i in range(STYLE_CACHE + 10):
        v.style(VoiceSpec(("a", "b"), (1.0, 1.0 + i)))
    assert len(v._styles) == STYLE_CACHE


def test_has_checks_every_name():
    v = kokoro_voice()
    assert v.has(VoiceSpec(("a", "b"), (1.0, 1.0)))
    assert not v.has(VoiceSpec(("a", "zz"), (1.0, 1.0)))


def test_blend_labels_do_not_depend_on_the_configured_voice():
    def blends(first):
        return {s.label() for s in catalogue(first) if len(s.names) == 2}

    assert blends("af_bella") == blends("af_heart")


def test_a_fifty_fifty_blend_takes_the_first_voices_accent():
    assert VoiceSpec(("af_heart", "bf_emma"), (0.5, 0.5)).lang == "en-us"


def test_a_repo_is_heard_only_in_its_own_voice(tmp_path):
    clock = Clock()
    running = {"1:1": True, "2:1": True}
    b = VoiceBook(tmp_path / "v.json", clock=clock, home_seconds=1000, alive=running.get)
    b.assign("1:1", "a")  # a's home: voice 0
    other = b.assign("2:1", "b")  # b's home: voice 1
    running["2:1"] = False  # b's terminal closes
    clock.now = 900
    b.assign("1:1", "b")  # a's terminal works in b, still speaking in a's voice
    clock.now = 1500  # b was last heard in its own voice at 0
    assert b.assign("3:1", "c") == other  # so b's voice is free for a new repo


def test_saves_resume_after_the_clock_jumps_back(tmp_path):
    clock = Clock()
    path = tmp_path / "v.json"
    b = VoiceBook(path, clock=clock, active_seconds=10**9)
    clock.now = 10_000
    b.assign("t1", "a")
    clock.now = 100  # jumped back
    b.assign("t1", "a")
    assert '"seen": 100' in path.read_text()


class FakeOrt:
    """Stands in for onnxruntime: CUDA is listed but cannot start unless `cuda_works`."""

    def __init__(self, providers, cuda_works=False, preload_fails=False):
        self.providers, self.cuda_works, self.preload_fails = providers, cuda_works, preload_fails
        self.started = []

    def preload_dlls(self):
        if self.preload_fails:
            raise OSError("libcudnn.so.9: cannot open shared object file")

    def set_default_logger_severity(self, level):
        pass

    class SessionOptions:
        log_severity_level = 0

    def get_available_providers(self):
        return self.providers

    def InferenceSession(self, path, options, providers):
        self.started.append(providers)
        if "CUDAExecutionProvider" in providers and not self.cuda_works:
            raise RuntimeError("Failed to load libcudnn")
        return providers


def test_cuda_that_will_not_start_falls_back_to_the_cpu(tmp_path):
    from keryx.voice import open_session

    ort = FakeOrt(["CUDAExecutionProvider", "CPUExecutionProvider"])
    assert open_session(ort, tmp_path / "m.onnx") == ["CPUExecutionProvider"]
    assert ort.started == [
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
        ["CPUExecutionProvider"],
    ]


def test_cuda_that_starts_is_used(tmp_path):
    from keryx.voice import open_session

    ort = FakeOrt(["CUDAExecutionProvider", "CPUExecutionProvider"], cuda_works=True)
    assert open_session(ort, tmp_path / "m.onnx")[0] == "CUDAExecutionProvider"


def test_a_cpu_failure_is_not_retried_or_hidden(tmp_path):
    from keryx.voice import open_session

    class Broken(FakeOrt):
        def InferenceSession(self, path, options, providers):
            raise RuntimeError("bad model file")

    with pytest.raises(RuntimeError, match="bad model"):
        open_session(Broken(["CPUExecutionProvider"]), tmp_path / "m.onnx")


def test_missing_cuda_libraries_do_not_stop_the_cpu_session(tmp_path):
    from keryx.voice import open_session

    ort = FakeOrt(["CUDAExecutionProvider", "CPUExecutionProvider"], preload_fails=True)
    assert open_session(ort, tmp_path / "m.onnx") == ["CPUExecutionProvider"]


def fake_curl(monkeypatch, payloads):
    """Make `curl -o PATH URL` write `payloads[name]`."""
    from pathlib import Path

    import keryx.voice as voice

    def run(cmd, check):
        out = Path(cmd[cmd.index("-o") + 1])
        out.write_bytes(payloads[cmd[-1].rsplit("/", 1)[1]])

    monkeypatch.setattr(voice.subprocess, "run", run)


def test_a_download_that_matches_its_checksum_is_kept(tmp_path, monkeypatch):
    import hashlib

    import keryx.voice as voice

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    payloads = {voice.MODEL: b"model", voice.VOICES: b"voices"}
    monkeypatch.setattr(
        voice, "CHECKSUMS", {n: hashlib.sha256(b).hexdigest() for n, b in payloads.items()}
    )
    fake_curl(monkeypatch, payloads)
    d = voice.ensure_models()
    assert (d / voice.MODEL).read_bytes() == b"model"
    assert not list(d.glob("*.part"))


def test_a_download_that_differs_is_discarded_and_refused(tmp_path, monkeypatch):
    import keryx.voice as voice

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    fake_curl(monkeypatch, {voice.MODEL: b"tampered", voice.VOICES: b"voices"})
    with pytest.raises(RuntimeError, match="checksum"):
        voice.ensure_models()
    d = voice.model_dir()
    assert not (d / voice.MODEL).exists() and not list(d.glob("*.part"))


def test_the_pinned_checksums_name_the_files_downloaded():
    import keryx.voice as voice

    assert set(voice.CHECKSUMS) == {voice.MODEL, voice.VOICES}
    assert all(len(h) == 64 for h in voice.CHECKSUMS.values())
