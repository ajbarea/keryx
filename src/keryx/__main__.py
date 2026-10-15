"""keryx: give Claude Code a voice.

keryx hook             read a Claude Code hook payload on stdin
keryx replay-hook      the same for the synchronous "say that again" prompt hook
keryx on | off         turn speech on or off
keryx status           show settings, daemon state and setup checks; exit 1 if one is missing
keryx say TEXT         speak TEXT as given
keryx again            say this terminal's last line again
keryx pronounce [WORD [SAYING]]   list, forget (WORD only) or set how to say WORD; /ipa/ = phonemes
keryx voice [NAME]     preview the voices and pick one, or set the one named (name or number)
keryx voices [N]       say a line in each of the first N voices in the catalogue
keryx stop             cut off current speech
keryx daemon           run the speech daemon in the foreground
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from keryx import client
from keryx.config import Config, set_stored

if TYPE_CHECKING:
    # Only for annotations (`from __future__ import annotations` keeps them unevaluated), so the
    # latency-sensitive hook path never imports voices.py; the runtime use is lazy in `_set_voice`.
    from keryx.voices import VoiceSpec

COMMANDS = (
    "hook",
    "replay-hook",
    "on",
    "off",
    "status",
    "say",
    "again",
    "pronounce",
    "voice",
    "voices",
    "stop",
    "daemon",
)


def _reconcile() -> bool:
    """Ping the daemon with our version, retiring one from an older keryx; spawns one if none
    runs. False (with a message) if none answers. Needed before any op a stale daemon would
    mishandle: `say` with an explicit voice, and `set_voice`, which an old daemon lacks."""
    from keryx import version

    try:
        client.current({"op": "ping", "version": version()})
        return True
    except (OSError, ValueError) as exc:
        print(f"the keryx daemon did not answer: {exc}", file=sys.stderr)
        return False


def _play(specs: list[VoiceSpec], line: Callable[[int, VoiceSpec], str]) -> None:
    """Say `line(n, spec)` in each spec's voice; print the daemon's error for any it refuses."""
    for n, spec in enumerate(specs, 1):
        request = {"op": "say", "kind": "notice", "text": line(n, spec), "voice": spec.label()}
        reply = client.send_or_spawn(request)
        if not reply.get("ok"):
            print(f"{spec.label()}: {reply.get('error')}", file=sys.stderr)


def _preview(specs: list[VoiceSpec]) -> bool:
    """List the voices on screen and say a sample line in each. False if no daemon answers."""
    if not _reconcile():
        return False
    for n, spec in enumerate(specs, 1):
        print(f"{n:2}. {spec.spoken()}")
    _play(specs, lambda n, spec: f"Voice {n}, {spec.spoken()}. This is how I read your replies.")
    return True


def _set_voice(cfg: Config, arg: str | None) -> int:
    """`keryx voice`: pick a voice by preview, or set the one named in `arg`."""
    from keryx.procs import terminal_id
    from keryx.voices import VoiceSpec, resolve, stock

    if not cfg.enabled:
        print("keryx is off; `keryx on` first", file=sys.stderr)
        return 1
    specs = stock(cfg.voice)
    choice = arg
    reconciled = False
    if choice is None:
        if not _preview(specs):  # reconciles, then plays each voice
            return 1
        reconciled = True
        if not sys.stdin.isatty():
            print("run `keryx voice <name or number>` to set one")
            return 0
        current = VoiceSpec((cfg.voice,)).spoken()
        try:
            choice = input(f"Pick a voice (number or name, Enter keeps {current}): ").strip()
        except EOFError:
            choice = ""
        if not choice:
            print("keeping the current voice")
            return 0
    label = resolve(choice, specs)
    if label is None:
        print(f"no voice matches {choice!r}; run `keryx voice` to hear them", file=sys.stderr)
        return 2
    # Retire a stale daemon (direct `keryx voice NAME` skips the preview that would have), so
    # it understands `set_voice` before config and daemon can diverge.
    if not reconciled and not _reconcile():
        return 1
    spoken = VoiceSpec.parse(label).spoken()
    try:
        reply = client.send_or_spawn({"op": "set_voice", "voice": label, "terminal": terminal_id()})
    except (OSError, ValueError) as exc:
        print(f"the daemon did not answer, voice unchanged: {exc}", file=sys.stderr)
        return 1
    if not reply.get("ok"):
        print(f"{label}: {reply.get('error')}", file=sys.stderr)
        return 1
    # Persist only a voice the daemon accepted, so a refusal never leaves config pointing at one.
    set_stored(voice=label)
    # The voice is set; a failed confirmation line must not crash the command.
    with contextlib.suppress(OSError, ValueError):
        client.send_or_spawn(
            {"op": "say", "kind": "notice", "text": f"Now speaking in {spoken}.", "voice": label}
        )
    # The pin is immediate; `voice` in config only leads new terminals once the daemon restarts.
    here = "this terminal now" if reply.get("pinned") else "after keryx restarts"
    print(f"voice set to {spoken}: {here}. New terminals follow once keryx restarts.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    cmd = args[0] if args else "status"
    cfg = Config.load()

    if cmd in ("hook", "replay-hook") and not cfg.enabled:
        return 0

    if cmd == "hook":
        from keryx import hook

        request = hook.request_for(hook.parse(sys.stdin.read()), hook.entrypoint())
        if request is None:
            return 0
        # Spawning on a prompt, not just a reply, loads the voice while Claude works.
        # No daemon to answer (turned off, or it failed to start): nothing to say.
        with contextlib.suppress(OSError, ValueError):  # ValueError: a truncated reply
            if request["op"] == "warm":
                client.current(request)
            else:
                client.send_or_spawn(request)
        return 0

    if cmd in ("on", "off"):
        # Only this key is written: neither env overrides nor defaults belong in the file.
        enabled = cmd == "on"
        set_stored(enabled=enabled)
        if not enabled:
            # Off frees the GPU: the daemon exits (releasing Kokoro) and the model unloads.
            with contextlib.suppress(OSError):
                client.send({"op": "quit"})
            if cfg.model:
                from keryx.summarize import OllamaClient

                with contextlib.suppress(OSError):
                    OllamaClient(cfg.model, cfg.ollama_host).unload()
        print(f"keryx is {cmd}")
        if Config.load().enabled != enabled:
            print("note: KERYX_ENABLED in the environment overrides this")
        return 0

    if cmd == "status":
        from keryx import doctor

        try:
            daemon = client.send({"op": "ping"})
        except (OSError, ValueError):
            daemon = None
        state = {**vars(cfg), "daemon": daemon or "not running"}
        print(json.dumps(state, indent=2))
        found = doctor.checks(cfg)
        print()
        print(doctor.render(found))
        return doctor.exit_code(found)

    if cmd == "say":
        if not cfg.enabled:
            print("keryx is off; `keryx on` first", file=sys.stderr)
            return 1
        text = " ".join(args[1:]) or sys.stdin.read()
        print(client.send_or_spawn({"op": "say", "kind": "notice", "text": text}))
        return 0

    if cmd == "voices":
        from keryx.voices import catalogue

        try:
            count = int(args[1]) if len(args) > 1 else 8
        except ValueError:
            count = 0
        if count < 1:
            print("usage: keryx voices [N], N a positive whole number", file=sys.stderr)
            return 2
        if not cfg.enabled:
            print("keryx is off; `keryx on` first", file=sys.stderr)
            return 1
        # Reconcile first: an older daemon would ignore `voice` and play every line in one voice.
        if not _reconcile():
            return 1
        _play(catalogue(cfg.voice)[:count], lambda n, spec: f"Voice {n}, {spec.spoken()}.")
        return 0

    if cmd == "voice":
        return _set_voice(cfg, args[1] if len(args) > 1 else None)

    if cmd == "replay-hook":
        # Synchronous UserPromptSubmit: "say that again" replays instead of reaching Claude.
        from keryx import hook
        from keryx.procs import terminal_id

        event = hook.parse(sys.stdin.read())
        if not hook.is_replay_event(event, hook.entrypoint()):
            return 0
        who = {"terminal": terminal_id(), "session": event.get("session_id", "")}
        try:
            replayed = client.send({"op": "again", **who}).get("replayed")
        except (OSError, ValueError):  # no daemon or a truncated reply
            replayed = False
        if replayed:
            print(json.dumps({"decision": "block", "reason": "keryx: saying that again"}))
            return 0
        # Claude answers, so this prompt is the turn the held-back stop request stood for.
        with contextlib.suppress(OSError, ValueError):
            client.send(hook.prompt_request(event))
        return 0

    if cmd == "again":
        from keryx.procs import terminal_id

        try:
            reply = client.send({"op": "again", "terminal": terminal_id()})
        except (OSError, ValueError):
            reply = {}
        print("saying it again" if reply.get("replayed") else "nothing to say again yet")
        return 0

    if cmd == "pronounce":
        from keryx import pronounce

        try:
            words = pronounce.load(strict=True)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        if len(args) == 1:
            for word, saying in sorted(words.items()):
                print(f"{word} -> {saying}")
            if not words:
                print("no pronunciations yet")
            return 0
        word, saying = args[1], " ".join(args[2:]).strip()
        saved = pronounce.same_word(words, word)
        if not saying:
            if saved is None:
                print(f"{word} had no pronunciation")
                return 0
            del words[saved]
            pronounce.save(words)
            print(f"forgot {saved}")
            return 0
        ipa = pronounce.phonemes(saying)
        unknown = pronounce.unknown_phonemes(ipa) if ipa else ""
        if unknown:
            print(f"Kokoro has no sound for {' '.join(unknown)}; not saved", file=sys.stderr)
            return 1
        if saved is not None:
            del words[saved]  # one entry per word, whatever its case
        words[word] = saying
        pronounce.save(words)
        print(f"{word} -> {saying}")
        with contextlib.suppress(OSError):
            client.send({"op": "say", "kind": "notice", "text": word})  # hear it once
        return 0

    if cmd == "stop":
        with contextlib.suppress(OSError):
            client.send({"op": "stop"})
        return 0

    if cmd == "daemon":
        import faulthandler

        faulthandler.enable()  # a native abort leaves its stack in daemon.stderr
        try:
            from keryx import daemon

            daemon.configure_logging(to_terminal=sys.stderr.isatty())
            return 0 if daemon.serve(cfg) else client.LOCK_BUSY_EXIT
        except Exception:
            logging.getLogger("keryx").exception("the daemon failed")
            return 1

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
