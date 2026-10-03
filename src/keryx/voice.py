"""Kokoro-82M through ONNX Runtime: CUDA when its runtime wheels are installed, else CPU."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from keryx.config import cache_dir
from keryx.loudness import TARGET_LUFS, normalize
from keryx.pronounce import PHONEMES_CLOSE, PHONEMES_OPEN
from keryx.voices import VoiceSpec

log = logging.getLogger("keryx")

RELEASE = "model-files-v1.0"
REPO = "thewh1teagle/kokoro-onnx"
MODEL = "kokoro-v1.0.onnx"
VOICES = "voices-v1.0.bin"
STYLE_CACHE = 64  # blends kept; each is about 0.5 MB
_SPLICE = re.compile(f"{PHONEMES_OPEN}([^{PHONEMES_CLOSE}]*){PHONEMES_CLOSE}")
# Closing and opening marks rejoin the word they belong to. ASCII quotes open and close
# alike, so they are left as they are.
_SPACE_BEFORE_MARK = re.compile(r"\s+([.,!?;:)\]}\u201d\u2019])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[{\u201c\u2018])\s+")
_POSSESSIVE = re.compile(r"^['\u2019]s\b")


def splice(text: str, phonemize) -> str | None:
    """`text` as phonemes, with each marked word's phonemes kept as given; None when
    nothing is marked, so plain text keeps Kokoro's own path."""
    parts = _SPLICE.split(text)
    if len(parts) == 1:
        return None
    # split() alternates text and captured phonemes: even indexes are text. A possessive
    # 's after a marked word is said as z, joined to it.
    for i in range(1, len(parts), 2):
        if i + 1 < len(parts) and _POSSESSIVE.match(parts[i + 1]):
            parts[i] += "z"
            parts[i + 1] = parts[i + 1][2:]
    out = [phonemize(p) if i % 2 == 0 else p for i, p in enumerate(parts) if p.strip()]
    joined = " ".join(o.strip() for o in out)
    return _SPACE_AFTER_OPEN.sub(r"\1", _SPACE_BEFORE_MARK.sub(r"\1", joined))


def model_dir() -> Path:
    return cache_dir() / "models"


def ensure_models() -> Path:
    """Fetch the model files once; ~350 MB."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in (MODEL, VOICES):
        if not (d / name).exists():
            url = f"https://github.com/{REPO}/releases/download/{RELEASE}/{name}"
            curl = ["curl", "-fsSL", "--connect-timeout", "20", "--max-time", "900"]
            subprocess.run([*curl, "-o", str(d / f"{name}.part"), url], check=True)
            (d / f"{name}.part").rename(d / name)
    return d


class KokoroVoice:
    def __init__(self, voice: str, speed: float, loudness: float = TARGET_LUFS):
        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        d = ensure_models()
        # Loads the pip-installed CUDA/cuDNN libraries; without them only CPU remains.
        ort.preload_dlls()
        ort.set_default_logger_severity(3)
        providers = [
            p
            for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
            if p in ort.get_available_providers()
        ]
        options = ort.SessionOptions()
        options.log_severity_level = 3  # the CUDA provider warns about memcpy nodes on load
        session = ort.InferenceSession(str(d / MODEL), options, providers=providers)
        self.provider = session.get_providers()[0]
        log.info("kokoro on %s", self.provider)
        self._kokoro = Kokoro.from_session(session, str(d / VOICES))
        self.voice = VoiceSpec((voice,))
        self.speed = speed
        self.loudness = loudness
        self._styles: dict[VoiceSpec, np.ndarray] = {}

    def has(self, spec: VoiceSpec) -> bool:
        return all(name in self._kokoro.voices for name in spec.names)

    def style(self, spec: VoiceSpec) -> np.ndarray:
        """A voice's style vectors; a blend is the weighted mean of its voices'."""
        if spec not in self._styles:
            # Scaled by the largest weight first, so huge weights cannot overflow to NaN.
            top = max(spec.weights)
            weights = [w / top for w in spec.weights]
            total = sum(weights)
            parts = [
                (w / total) * self._kokoro.get_voice_style(n).astype(np.float64)
                for n, w in zip(spec.names, weights, strict=True)
            ]
            if len(self._styles) >= STYLE_CACHE:
                self._styles.pop(next(iter(self._styles)))
            self._styles[spec] = sum(parts).astype(np.float32)
        return self._styles[spec]

    def synth(self, text: str, voice: VoiceSpec | None = None) -> tuple[np.ndarray, int]:
        spec = voice or self.voice
        spliced = splice(text, lambda part: self._kokoro.tokenizer.phonemize(part, spec.lang))
        samples, rate = self._kokoro.create(
            text if spliced is None else spliced,
            voice=self.style(spec),
            speed=self.speed,
            lang=spec.lang,
            is_phonemes=spliced is not None,
        )
        # Kokoro's voices range from -19 to -23 LUFS; level them, loud enough for over music.
        return normalize(samples, rate, self.loudness), rate


def write_wav(path: Path, samples: np.ndarray, rate: int) -> float:
    """Write 16-bit PCM (what MCI's waveaudio plays) and return its length in seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples, rate, subtype="PCM_16")
    return len(samples) / rate
