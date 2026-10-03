"""User settings in `$XDG_CONFIG_HOME/keryx/config.json`, with env overrides."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import asdict, dataclass, field, fields
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
    # Every sentence is brought to this integrated loudness (LUFS) before it plays.
    loudness: float = -16.0
    model: str = "gemma3:4b"
    ollama_host: str = "http://localhost:11434"
    # Apps (Windows process names) turned down to `duck_ratio` of their volume while speaking.
    duck_apps: list[str] = field(default_factory=lambda: ["Spotify"])
    duck_ratio: float = 0.25
    # Spoken WAVs are written here because Windows can only play from its own drives.
    audio_dir: str = "/mnt/c/Windows/Temp/keryx"

    @classmethod
    def load(cls, env: bool = True) -> Config:
        """Settings from the file, then `KERYX_*` env overrides unless `env` is False."""
        raw = read_raw()
        defaults = cls()
        # A value of the wrong type (a string where a list belongs) falls back to the default.
        cfg = cls(
            **{
                f.name: raw[f.name]
                for f in fields(cls)
                if f.name in raw and _fits(raw[f.name], getattr(defaults, f.name))
            }
        )
        for f in fields(cls) if env else ():
            value = os.environ.get(f"KERYX_{f.name.upper()}")
            if value is not None:
                # By the default's type: a file value such as `1` for a float must not make
                # `KERYX_SPEED=1.3` an int.
                with contextlib.suppress(ValueError):
                    setattr(cfg, f.name, _coerce(value, type(getattr(defaults, f.name))))
        return cfg

    def save(self) -> None:
        write_raw(asdict(self))


def config_path() -> Path:
    return config_dir() / "config.json"


def read_raw() -> dict:
    """The file's JSON object; empty when it is missing, unreadable or not an object."""
    try:
        raw = json.loads(config_path().read_text())
    except (OSError, ValueError):  # ValueError: bad JSON or bytes that are not UTF-8
        return {}
    return raw if isinstance(raw, dict) else {}


def write_raw(raw: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2) + "\n")


def set_stored(**changes: object) -> None:
    """Write `changes` into the file, leaving its other keys, and the defaults, as they are.

    A file that cannot be read as an object is kept as `config.json.bad` first.
    """
    path = config_path()
    raw: dict = {}
    try:
        text = path.read_text()
        loaded = json.loads(text) if text.strip() else {}
        if isinstance(loaded, dict):
            raw = loaded
        else:
            raise ValueError("not an object")
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        with contextlib.suppress(OSError):
            path.replace(path.with_name(path.name + ".bad"))
    write_raw({**raw, **changes})


def _fits(value: object, default: object) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, int | float) and not isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    return isinstance(value, type(default))


def _coerce(value: str, kind: type) -> object:
    if kind is bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if kind is list:
        return [part.strip() for part in value.split(",") if part.strip()]
    return kind(value)
