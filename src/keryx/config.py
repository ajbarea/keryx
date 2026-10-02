"""User settings in `$XDG_CONFIG_HOME/keryx/config.json`, with env overrides."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "keryx"


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "keryx"


def socket_path() -> Path:
    return cache_dir() / "keryx.sock"


@dataclass
class Config:
    enabled: bool = True
    voice: str = "af_heart"
    # Give each terminal its own voice; `voice` is the first one handed out.
    distinct_voices: bool = True
    speed: float = 1.0
    model: str = "gemma3:4b"
    ollama_host: str = "http://localhost:11434"
    # Spoken WAVs are written here because Windows can only play from its own drives.
    audio_dir: str = "/mnt/c/Windows/Temp/keryx"

    @classmethod
    def load(cls, env: bool = True) -> Config:
        """Settings from the file, then `KERYX_*` env overrides unless `env` is False."""
        path = config_dir() / "config.json"
        try:
            raw = json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        known = {f.name for f in fields(cls)}
        cfg = cls(**{k: v for k, v in raw.items() if k in known})
        for f in fields(cls) if env else ():
            value = os.environ.get(f"KERYX_{f.name.upper()}")
            if value is not None:
                with contextlib.suppress(ValueError):
                    setattr(cfg, f.name, _coerce(value, type(getattr(cfg, f.name))))
        return cfg

    def save(self) -> None:
        path = config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n")


def _coerce(value: str, kind: type) -> object:
    if kind is bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return kind(value)
