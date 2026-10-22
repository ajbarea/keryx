"""Is there room to load the summarizer? Probes for free memory; each answers None when unknown."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from collections.abc import Callable
from pathlib import Path

NVIDIA_SMI = ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"]
PROBE_TIMEOUT = 2


def mem_available_mb(meminfo: Path = Path("/proc/meminfo")) -> int | None:
    """MemAvailable in MiB, or None when the file is unreadable or lacks it."""
    try:
        lines = meminfo.read_text().splitlines()
    except (OSError, ValueError):
        return None
    for line in lines:
        if line.startswith("MemAvailable:"):
            parts = line.split()
            try:
                return int(parts[1]) // 1024
            except (IndexError, ValueError):
                return None
    return None


def gpu_free_mb(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> int | None:
    """Free memory of the roomiest GPU in MiB (Ollama can use any), or None without a reading."""
    try:
        done = run(NVIDIA_SMI, capture_output=True, text=True, timeout=PROBE_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    readings = [int(line) for line in (done.stdout or "").split() if line.strip().isdigit()]
    return max(readings, default=None)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as resp:
        return resp.read()


def model_loaded(host: str, model: str, fetch: Callable[[str], bytes] = _get) -> bool:
    """True when Ollama's /api/ps lists `model` (or `model:latest`); False on any error."""
    try:
        listed = json.loads(fetch(f"{host.rstrip('/')}/api/ps"))["models"]
        names = {m.get(key) for m in listed for key in ("name", "model")}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False
    return model in names or f"{model}:latest" in names


def low_memory(min_ram_mb: int, min_vram_mb: int, ram: int | None, vram: int | None) -> str | None:
    """Why loading the model is unwise, or None. An unknown reading or a 0 threshold passes."""
    if min_ram_mb > 0 and ram is not None and ram < min_ram_mb:
        return f"RAM {ram} MiB free < {min_ram_mb}"
    if min_vram_mb > 0 and vram is not None and vram < min_vram_mb:
        return f"GPU {vram} MiB free < {min_vram_mb}"
    return None
