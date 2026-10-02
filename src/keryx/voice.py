"""Kokoro-82M through ONNX Runtime: CUDA when its runtime wheels are installed, else CPU."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from keryx.config import cache_dir

log = logging.getLogger("keryx")

RELEASE = "model-files-v1.0"
REPO = "thewh1teagle/kokoro-onnx"
MODEL = "kokoro-v1.0.onnx"
VOICES = "voices-v1.0.bin"


def model_dir() -> Path:
    return cache_dir() / "models"


def ensure_models() -> Path:
    """Fetch the model files once; ~350 MB."""
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in (MODEL, VOICES):
        if not (d / name).exists():
            url = f"https://github.com/{REPO}/releases/download/{RELEASE}/{name}"
            subprocess.run(["curl", "-fsSL", "-o", str(d / f"{name}.part"), url], check=True)
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
        self.voice = voice
        self.speed = speed

    def synth(self, text: str) -> tuple[np.ndarray, int]:
        samples, rate = self._kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        return samples, rate


def write_wav(path: Path, samples: np.ndarray, rate: int) -> float:
    """Write 16-bit PCM (what `SoundPlayer` accepts) and return its length in seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples, rate, subtype="PCM_16")
    return len(samples) / rate
