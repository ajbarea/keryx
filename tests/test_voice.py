import numpy as np
import pytest
import soundfile as sf

from keryx.voice import default_voice, render_wav
from keryx.voices import POOL, VoiceSpec


def test_a_real_kokoro_voice_is_kept():
    assert default_voice("bf_emma", {"af_heart", "bf_emma", "am_puck"}) == "bf_emma"


def test_a_typo_or_missing_voice_falls_back_to_the_pool_lead():
    assert default_voice("af_tpyo", {"af_heart", "bf_emma"}) == POOL[0]


def test_a_voice_removed_from_kokoro_falls_back():
    # If Kokoro lacked af_nicole, the default-synth path must fall back, not fail.
    assert default_voice("af_nicole", {"af_heart", "af_bella"}) == POOL[0]


class StubEngine:
    def __init__(self, sample_rate=24000, samples_per_sentence=240):
        self.sample_rate = sample_rate
        self.samples_per_sentence = samples_per_sentence
        self.calls = []

    def synth(self, text, voice=None):
        self.calls.append((text, voice))
        return np.ones(self.samples_per_sentence, dtype=np.float32) * 0.5, self.sample_rate


def test_render_wav_concatenates_sentences_with_gap(tmp_path):
    engine = StubEngine(sample_rate=24000, samples_per_sentence=240)
    out = tmp_path / "sub" / "track.wav"
    spec = VoiceSpec(("am_michael",))

    dur = render_wav("First sentence. Second sentence.", out, spec, engine, gap_seconds=0.25)
    assert out.exists()
    assert dur > 0

    data, rate = sf.read(out)
    assert rate == 24000
    # Expected samples: 240 + round(24000 * 0.25) + 240 = 240 + 6000 + 240 = 6480
    assert len(data) == 6480
    assert len(engine.calls) == 2
    assert engine.calls[0][0] == "First sentence."
    assert engine.calls[1][0] == "Second sentence."


def test_render_wav_applies_pronounce(tmp_path):
    engine = StubEngine()
    out = tmp_path / "track.wav"
    spec = VoiceSpec(("af_heart",))

    render_wav(
        "Check ajsoftworks repo.",
        out,
        spec,
        engine,
        pronounce=lambda s: s.replace("ajsoftworks", "AJ soft works"),
    )
    assert engine.calls[0][0] == "Check AJ soft works repo."


def test_render_wav_cleans_tmp_on_failure(tmp_path):
    class FailingEngine:
        def __init__(self):
            self.count = 0

        def synth(self, text, voice=None):
            self.count += 1
            if self.count > 1:
                raise RuntimeError("synth exploded")
            return np.zeros(240, dtype=np.float32), 24000

    out = tmp_path / "failed.wav"
    spec = VoiceSpec(("af_heart",))

    with pytest.raises(RuntimeError, match="synth exploded"):
        render_wav("Sentence one. Sentence two.", out, spec, FailingEngine())

    assert not out.exists()
    assert list(tmp_path.glob(".tmp-*")) == []


def test_render_wav_refuses_empty_text(tmp_path):
    engine = StubEngine()
    out = tmp_path / "empty.wav"
    spec = VoiceSpec(("af_heart",))

    with pytest.raises(ValueError, match="empty text"):
        render_wav("   ", out, spec, engine)

    assert not out.exists()
