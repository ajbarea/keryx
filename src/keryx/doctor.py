"""Setup checks `keryx status` prints, one line each in the techne doctor format."""

from __future__ import annotations

import http.client
import json
import re
import shlex
import shutil
import subprocess
import urllib.request
from collections.abc import Callable
from typing import NamedTuple

from keryx.config import Config

UV_INSTALL = "curl -LsSf https://astral.sh/uv/install.sh | sh"
OLLAMA_INSTALL = "curl -fsSL https://ollama.com/install.sh | sh"
DEFAULT_AUDIO_DIR = Config().audio_dir
WINDOWS_DRIVE = re.compile(r"^/mnt/[a-z](/|$)")
TIMEOUT = 2.0
TUNED_KV_CACHE = ("q8_0", "q4_0")
MEMORY_FIX = (
    "fix: sudo systemctl edit ollama  # add OLLAMA_KV_CACHE_TYPE=q8_0 and"
    " OLLAMA_FLASH_ATTENTION=1; see docs/troubleshooting.md#ollama-server-memory"
)


class Check(NamedTuple):
    status: str
    name: str
    detail: str
    fixes: tuple[str, ...] = ()


Which = Callable[[str], str | None]
Fetch = Callable[[str], bytes]
ServerEnv = Callable[[], dict[str, str] | None]


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
        return resp.read()


def _systemd_env(run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run):
    """The OLLAMA_* variables of the `ollama` systemd unit, or None when it is not one."""

    def show(prop: str) -> str:
        done = run(
            ["systemctl", "show", "ollama", "-p", prop, "--value"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        if done.returncode != 0:
            raise OSError(f"systemctl exited {done.returncode}")
        return done.stdout.strip()

    try:
        if show("LoadState") == "not-found":
            return None
        assignments = shlex.split(show("Environment"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    pairs = (a.partition("=") for a in assignments)
    return {k: v for k, _, v in pairs if k.startswith("OLLAMA_") and k.isupper()}


def _memory(env: dict[str, str] | None) -> Check:
    if env is None:
        return Check(
            "n/a", "ollama-memory", "not a systemd service; see the docs for its memory settings"
        )
    kv, flash, keep = (
        env.get(k) for k in ("OLLAMA_KV_CACHE_TYPE", "OLLAMA_FLASH_ATTENTION", "OLLAMA_KEEP_ALIVE")
    )
    detail = (
        f"kv_cache={kv or 'f16 (unset)'}, flash_attention={flash or 'auto (unset)'},"
        f" keep_alive={keep or '5m (unset)'}"
    )
    if kv in TUNED_KV_CACHE and flash:
        return Check("ok", "ollama-memory", detail)
    return Check("optional", "ollama-memory", detail, (MEMORY_FIX,))


def _loaded(fetch: Fetch, host: str) -> Check:
    try:
        models = json.loads(fetch(f"{host}/api/ps")).get("models", [])
        shown = [
            f"{m['name']} (context {m['context_length']}, {m['size_vram'] / 1024**3:.1f} GB GPU)"
            for m in models
        ]
    except (OSError, ValueError, AttributeError, KeyError, TypeError, http.client.HTTPException):
        return Check("n/a", "ollama-loaded", "could not read /api/ps")
    return Check("ok", "ollama-loaded", ", ".join(shown) or "none")


def _program(name: str, which: Which, detail: str, fixes: tuple[str, ...]) -> Check:
    found = which(name)
    return Check("ok", name, found) if found else Check("missing", name, detail, fixes)


def checks(
    cfg: Config,
    which: Which = shutil.which,
    fetch: Fetch = _fetch,
    server_env: ServerEnv = _systemd_env,
) -> list[Check]:
    found = [
        _program("uv", which, "not on PATH", (f"fix: {UV_INSTALL}",)),
        _program(
            "powershell.exe",
            which,
            "not on PATH; keryx plays audio through Windows, so it runs on WSL2 only",
            (),
        ),
    ]
    host = cfg.ollama_host.rstrip("/")
    if not cfg.model:
        found += [Check("n/a", n, "no summarizer model is set") for n in ("ollama", "model")]
    else:
        try:
            fetch(f"{host}/api/version")
            tags = json.loads(fetch(f"{host}/api/tags")).get("models", [])
            names = {m.get("name", "") for m in tags}
        except (OSError, ValueError, AttributeError, http.client.HTTPException) as exc:
            fix = "fix: ollama serve" if which("ollama") else f"fix: {OLLAMA_INSTALL}"
            found.append(Check("missing", "ollama", f"{host} did not answer ({exc})", (fix,)))
            found.append(Check("n/a", "model", "Ollama is not reachable"))
        else:
            found.append(Check("ok", "ollama", f"{host} answers"))
            pulled = cfg.model in names or f"{cfg.model}:latest" in names
            found.append(
                Check("ok", "model", cfg.model)
                if pulled
                else Check(
                    "missing",
                    "model",
                    f"{cfg.model} is not pulled",
                    (f"fix: ollama pull {cfg.model}",),
                )
            )
            found += [_memory(server_env()), _loaded(fetch, host)]
    if WINDOWS_DRIVE.match(cfg.audio_dir):
        found.append(Check("ok", "audio-dir", cfg.audio_dir))
    else:
        found.append(
            Check(
                "missing",
                "audio-dir",
                f"{cfg.audio_dir} is not on a Windows drive;"
                " Windows plays only from its own drives",
                (f"fix: export KERYX_AUDIO_DIR={DEFAULT_AUDIO_DIR}",),
            )
        )
    return found


def render(found: list[Check]) -> str:
    lines = []
    for check in found:
        lines.append(f"{check.status} {check.name}: {check.detail}")
        if check.status in ("missing", "optional"):
            lines.extend(f"  {fix}" for fix in check.fixes)
    missing = [c.name for c in found if c.status == "missing"]
    lines.append("result: missing " + ", ".join(missing) if missing else "result: ready")
    return "\n".join(lines)


def exit_code(found: list[Check]) -> int:
    return 1 if any(c.status == "missing" for c in found) else 0
