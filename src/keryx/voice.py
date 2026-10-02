"""Kokoro-82M through ONNX Runtime: CUDA when its runtime wheels are installed, else CPU."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from keryx.config import cache_dir
from keryx.voices import VoiceSpec

log = logging.getLogger("keryx")

RELEASE = "model-files-v1.0"
REPO = "thewh1teagle/kokoro-onnx"
MODEL = "kokoro-v1.0.onnx"
VOICES = "voices-v1.0.bin"
STYLE_CACHE = 64  # blends kept; each is about 0.5 MB


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
    def __init__(self, voice: str, speed: float):
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
        samples, rate = self._kokoro.create(
            text, voice=self.style(spec), speed=self.speed, lang=spec.lang
        )
        return samples, rate


def write_wav(path: Path, samples: np.ndarray, rate: int) -> float:
    """Write 16-bit PCM (what `SoundPlayer` accepts) and return its length in seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples, rate, subtype="PCM_16")
    return len(samples) / rate
