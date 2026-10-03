import numpy as np
import pytest

from keryx.loudness import CEILING_DBFS, TARGET_LUFS, limit, loudness, normalize

RATE = 24000


def speechlike(seconds=2.0, level=0.05, seed=0):
    """Noise shaped by a slow syllable-rate envelope, a stand-in for speech."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * RATE)) / RATE
    envelope = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t) ** 2
    return (level * envelope * rng.standard_normal(t.size)).astype(np.float32)


@pytest.mark.parametrize("level", [0.01, 0.05, 0.3])
def test_quiet_and_loud_clips_land_on_the_target(level):
    out = normalize(speechlike(level=level), RATE)
    assert loudness(out, RATE) == pytest.approx(TARGET_LUFS, abs=1.0)


def test_peaks_never_pass_the_ceiling():
    clip = speechlike(level=0.05)
    clip[RATE // 2] = 0.9  # a click far above the rest
    out = normalize(clip, RATE)
    assert np.abs(out).max() <= 10 ** (CEILING_DBFS / 20) + 1e-6


def test_the_limiter_leaves_quiet_audio_alone():
    clip = speechlike(level=0.01)
    assert np.array_equal(limit(clip, RATE), clip)


def test_a_clip_shorter_than_one_gating_block_is_still_measured():
    out = normalize(speechlike(seconds=0.2), RATE)
    assert np.isfinite(loudness(out, RATE))
    assert out.size == int(0.2 * RATE)


def test_silence_and_empty_clips_come_back_as_given():
    silence = np.zeros(RATE, dtype=np.float32)
    assert np.array_equal(normalize(silence, RATE), silence)
    assert normalize(np.zeros(0, dtype=np.float32), RATE).size == 0


def test_the_dtype_is_kept():
    assert normalize(speechlike(), RATE).dtype == np.float32


def test_a_short_clip_measures_like_a_long_one():
    t = np.arange(RATE) / RATE
    tone = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert loudness(tone[: RATE // 5], RATE) == pytest.approx(loudness(tone, RATE), abs=0.3)
