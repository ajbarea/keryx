"""Make every spoken sentence equally loud, and loud enough to be heard over music.

Each sentence is normalized to an integrated loudness (ITU-R BS.1770, through pyloudnorm),
then a lookahead limiter keeps its peaks under a ceiling. Speech is usually mastered to
-16 to -18 LUFS with true peaks at or below -1 dBTP (EBU R 128; research 2026-10); the
ceiling here is sample-peak with half a dB of margin for the peaks between samples.
"""

from __future__ import annotations

import functools
import math

import numpy as np

TARGET_LUFS = -16.0
CEILING_DBFS = -1.5
LOOKAHEAD_SECONDS = 0.005
BLOCK_SECONDS = 0.4  # BS.1770's gating block; a shorter clip is padded with silence to it


@functools.cache
def _meter(rate: int):
    import pyloudnorm

    return pyloudnorm.Meter(rate)


def loudness(samples: np.ndarray, rate: int) -> float:
    """Integrated loudness in LUFS; -inf for silence.

    A clip shorter than one gating block is padded with silence to measure it. The padding
    dilutes the block's mean square by len/block, so the reading is raised by that ratio.
    """
    block = int(BLOCK_SECONDS * rate)
    if samples.size == 0:
        return float("-inf")
    if len(samples) >= block:
        return float(_meter(rate).integrated_loudness(samples.astype(np.float64)))
    padded = np.pad(samples.astype(np.float64), (0, block - len(samples)))
    measured = float(_meter(rate).integrated_loudness(padded))
    return measured + 10 * math.log10(block / len(samples)) if math.isfinite(measured) else measured


def limit(samples: np.ndarray, rate: int, ceiling_dbfs: float = CEILING_DBFS) -> np.ndarray:
    """Turn down only the stretches whose peaks pass the ceiling, starting just before them.

    The gain at each sample is the smallest gain needed anywhere within twice the lookahead,
    smoothed over the lookahead; every term of that average is at most the gain the sample
    itself needs, so no sample can end above the ceiling.
    """
    from scipy.ndimage import minimum_filter1d, uniform_filter1d

    ceiling = 10 ** (ceiling_dbfs / 20)
    peaks = np.abs(samples)
    if peaks.size == 0 or peaks.max() <= ceiling:
        return samples
    need = np.minimum(1.0, ceiling / np.maximum(peaks, 1e-12))
    span = max(1, int(LOOKAHEAD_SECONDS * rate))
    gain = uniform_filter1d(minimum_filter1d(need, size=2 * span + 1), size=span)
    return np.clip(samples * np.minimum(gain, need), -ceiling, ceiling).astype(samples.dtype)


def normalize(samples: np.ndarray, rate: int, target_lufs: float = TARGET_LUFS) -> np.ndarray:
    """`samples` at `target_lufs`, peaks limited; silence and empty clips come back as given."""
    if samples.size == 0:
        return samples
    measured = loudness(samples, rate)
    if not math.isfinite(measured):
        return samples
    gain = 10 ** ((target_lufs - measured) / 20)
    return limit((samples * gain).astype(samples.dtype), rate)
