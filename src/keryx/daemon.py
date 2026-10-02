"""The long-lived process: keeps Kokoro loaded and serves requests on a Unix socket.

Requests are one JSON object per connection, answered with one JSON line:
`{"op": "say", "text", "kind", "session", "source"}`, `{"op": "stop", "session"}`,
`{"op": "ping"}`, `{"op": "quit"}`.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
import socket
import threading
import time
from collections.abc import Callable
from pathlib import Path

from keryx.client import read_all
from keryx.config import Config, socket_path
from keryx.player import WindowsPlayer
from keryx.speaker import Speaker, SpeechQueue, Utterance, slot_names
from keryx.summarize import OllamaClient, spoken_line
from keryx.voice import KokoroVoice

log = logging.getLogger("keryx")

IDLE_EXIT_SECONDS = 4 * 3600


def handle(
    request: dict,
    speaker: SpeechQueue,
    warm: Callable[[], None] | None = None,
    latest_prompt: dict[str, str] | None = None,
) -> dict:
    """`latest_prompt` maps session to its newest prompt id, to drop replies that lost a race."""
    latest = latest_prompt if latest_prompt is not None else {}
    op = request.get("op")
    if op == "ping":
        return {"ok": True, "pid": os.getpid()}
    if op == "quit":
        speaker.stop()
        return {"ok": True, "quit": True}
    if op == "stop":
        if request.get("session") and request.get("prompt"):
            latest[request["session"]] = request["prompt"]
        speaker.stop(request.get("session") or None)
        # A prompt was just sent, so a reply is coming: load the summarizer meanwhile.
        if request.get("warm") and warm is not None:
            threading.Thread(target=warm, daemon=True).start()
        return {"ok": True}
    if op == "say":
        text = str(request.get("text") or "")
        if not text.strip():
            return {"ok": False, "error": "empty text"}
        # Hooks are async: a reply's hook can land after the next prompt's. That reply is
        # stale and would talk over the new turn.
        session, prompt = request.get("session"), request.get("prompt")
        if session and prompt and latest.get(session, prompt) != prompt:
            return {"ok": True, "dropped": "stale"}
        speaker.submit(
            Utterance(
                text=text,
                kind="notice" if request.get("kind") == "notice" else "reply",
                session=str(request.get("session") or ""),
                source=str(request.get("source") or ""),
            )
        )
        return {"ok": True}
    return {"ok": False, "error": f"unknown op {op!r}"}


def build_speaker(cfg: Config) -> tuple[Speaker, WindowsPlayer, Callable[[], None] | None]:
    client = OllamaClient(cfg.model, cfg.ollama_host) if cfg.model else None

    def warm() -> None:
        assert client is not None
        try:
            client.warm()
        except OSError as exc:
            log.warning("could not warm %s: %s", cfg.model, exc)

    def shorten(text: str) -> str:
        started = time.monotonic()
        line = spoken_line(text, client)
        log.info("shortened %d chars to %r in %.2fs", len(text), line, time.monotonic() - started)
        return line

    player = WindowsPlayer()
    voice = KokoroVoice(cfg.voice, cfg.speed)
    speaker = Speaker(shorten, voice, player, Path(cfg.audio_dir))
    return speaker, player, warm if client else None


def serve(
    cfg: Config,
    sock_path: Path | None = None,
    speaker: SpeechQueue | None = None,
    warm: Callable[[], None] | None = None,
    idle_exit: float = IDLE_EXIT_SECONDS,
    poll: float = 60.0,
) -> None:
    sock_path = sock_path or socket_path()
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    # One daemon per socket. Without this, a second daemon would unlink the socket and
    # take it over, leaving the first one running where nobody can reach it.
    lock = open(sock_path.with_suffix(".lock"), "w")  # noqa: SIM115 - held for the lifetime
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.info("another daemon already owns %s", sock_path)
        lock.close()
        return
    try:
        _serve_locked(cfg, sock_path, speaker, warm, idle_exit, poll)
    finally:
        lock.close()


def _serve_locked(
    cfg: Config,
    sock_path: Path,
    speaker: SpeechQueue | None,
    warm: Callable[[], None] | None,
    idle_exit: float,
    poll: float,
) -> None:
    with contextlib.suppress(FileNotFoundError):
        sock_path.unlink()
    player = None
    if speaker is None:
        speaker, player, warm = build_speaker(cfg)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    os.chmod(sock_path, 0o600)
    server.listen(16)
    server.settimeout(poll)
    log.info("listening on %s (voice=%s, model=%s)", sock_path, cfg.voice, cfg.model)
    last_activity = time.monotonic()
    latest_prompt: dict[str, str] = {}
    try:
        while True:
            try:
                conn, _ = server.accept()
            except TimeoutError:
                if speaker.idle() and time.monotonic() - last_activity > idle_exit:
                    log.info("idle for %ds, exiting", idle_exit)
                    return
                continue
            last_activity = time.monotonic()
            with conn:
                conn.settimeout(5)
                request: object = None
                try:
                    request = json.loads(read_all(conn))
                    reply = (
                        handle(request, speaker, warm, latest_prompt)
                        if isinstance(request, dict)
                        else {"ok": False}
                    )
                except (json.JSONDecodeError, OSError) as exc:
                    reply = {"ok": False, "error": str(exc)}
                log.info("%s -> %s", request_summary(request), reply)
                with contextlib.suppress(OSError):
                    conn.sendall((json.dumps(reply) + "\n").encode())
            if reply.get("quit"):
                log.info("quit requested")
                return
    finally:
        server.close()
        with contextlib.suppress(FileNotFoundError):
            sock_path.unlink()
        speaker.stop()
        speaker.close()
        if player is not None:
            player.close()
            remove_slots(Path(cfg.audio_dir))


def remove_slots(audio_dir: Path) -> None:
    """Delete keryx's own slot files; anything else in `audio_dir` is left alone."""
    for name in slot_names():
        with contextlib.suppress(OSError):
            (audio_dir / name).unlink()


def request_summary(request: object) -> str:
    if not isinstance(request, dict):
        return "bad request"
    text = str(request.get("text") or "")
    return f"{request.get('op')} {request.get('source', '')} {len(text)} chars".strip()
