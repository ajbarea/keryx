"""User settings in `$XDG_CONFIG_HOME/keryx/config.json`, with env overrides."""

from __future__ import annotations

import contextlib
import json
import logging
import math
import os
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger("keryx")

# Go's duration units, which Ollama's `keep_alive` uses, in seconds.
_UNITS = {
    "ns": 1e-9,
    "us": 1e-6,
    "µs": 1e-6,
    "μs": 1e-6,
    "ms": 1e-3,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
}
_DURATION_PART = re.compile(r"(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)")


def config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "keryx"


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "keryx"


def log_dir() -> Path:
    """Where the daemon's logs live: XDG state data, not cache, so clearing a cache keeps them."""
    return (
        Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "keryx" / "log"
    )


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
    # How long Ollama keeps the summarizer loaded after its last use; "0" unloads after every reply.
    keep_alive: str = "5m"
    # With the model not loaded and less than this free, replies are trimmed, not summarized;
    # 0 turns the check off. RAM: the model's 1.22 GB peak RSS plus earlyoom's 0.5 GB floor.
    min_free_ram_mb: int = 2048
    # GPU memory (MiB): loading gemma3:4b took 3.8 GB, plus margin.
    min_free_vram_mb: int = 4096
    # Apps (Windows process names) turned down to `duck_ratio` of their volume while speaking.
    duck_apps: list[str] = field(default_factory=lambda: ["Spotify"])
    duck_ratio: float = 0.25
    # Write speaking.json into klepsydra's fleet folder (when it exists) as each clip plays.
    speaking_signal: bool = True
    # Keep each session's latest reply as one WAV beside klepsydra's fleet folder (when it exists).
    reply_clips: bool = True
    # Spoken WAVs are written here because Windows can only play from its own drives.
    audio_dir: str = "/mnt/c/Windows/Temp/keryx"

    @classmethod
    def load(cls, env: bool = True) -> Config:
        """Settings from the file, then `KERYX_*` env overrides unless `env` is False."""
        raw = read_raw()
        # JSON `0` or `300` (seconds) is as good as "0" or "300".
        if isinstance(raw.get("keep_alive"), int | float) and not isinstance(
            raw["keep_alive"], bool
        ):
            raw["keep_alive"] = str(raw["keep_alive"])
        defaults = cls()
        # A value of the wrong type (a string where a list belongs) falls back to the default.
        misfits = [
            f.name
            for f in fields(cls)
            if f.name in raw and not _fits(raw[f.name], getattr(defaults, f.name))
        ]
        for name in misfits:
            log.warning(
                "config.json %s=%r is not a %s; using %r",
                name,
                raw[name],
                type(getattr(defaults, name)).__name__,
                getattr(defaults, name),
            )
        cfg = cls(
            **{f.name: raw[f.name] for f in fields(cls) if f.name in raw and f.name not in misfits}
        )
        for f in fields(cls) if env else ():
            value = os.environ.get(f"KERYX_{f.name.upper()}")
            if value is not None:
                # By the default's type: a file value such as `1` for a float must not make
                # `KERYX_SPEED=1.3` an int.
                kind = type(getattr(defaults, f.name))
                try:
                    setattr(cfg, f.name, _coerce(value, kind))
                except ValueError:
                    log.warning(
                        "KERYX_%s=%r is not a %s; using %r",
                        f.name.upper(),
                        value,
                        kind.__name__,
                        getattr(cfg, f.name),
                    )
        if keep_alive_seconds(cfg.keep_alive) is None:
            log.warning(
                "keep_alive %r is not seconds or a duration such as 10m; using %s",
                cfg.keep_alive,
                defaults.keep_alive,
            )
            cfg.keep_alive = defaults.keep_alive
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


def keep_alive_seconds(value: str) -> float | None:
    """`value` (seconds, or a Go duration such as `1h30m`) in seconds; None when it is neither."""
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        sign = -1.0 if text.startswith("-") else 1.0
        body = text[1:] if text[:1] in "+-" else text
        parts = _DURATION_PART.findall(body)
        if not body or "".join(n + u for n, u in parts) != body:
            return None
        seconds = sign * sum(float(n) * _UNITS[u] for n, u in parts)
    return seconds if math.isfinite(seconds) else None


def _fits(value: object, default: object) -> bool:
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, float):
        return isinstance(value, int | float) and not isinstance(value, bool)
    if isinstance(default, list):
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, type(default))


def _coerce(value: str, kind: type) -> object:
    if kind is bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if kind is list:
        return [part.strip() for part in value.split(",") if part.strip()]
    return kind(value)
