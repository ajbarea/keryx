"""keryx: give Claude Code a voice.

keryx hook             read a Claude Code hook payload on stdin
keryx replay-hook      the same for the synchronous "say that again" prompt hook
keryx on | off         turn speech on or off
keryx status           show settings and whether the daemon is up
keryx say TEXT         speak TEXT as given
keryx again            say this terminal's last line again
keryx pronounce [WORD [SAYING]]   list, forget (WORD only) or set how to say WORD; /ipa/ = phonemes
keryx voices [N]       say a line in each of the first N voices in the catalogue
keryx stop             cut off current speech
keryx daemon           run the speech daemon in the foreground
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys

from keryx import client
from keryx.config import Config, set_stored

COMMANDS = (
    "hook",
    "replay-hook",
    "on",
    "off",
    "status",
    "say",
    "again",
    "pronounce",
    "voices",
    "stop",
    "daemon",
)


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
        try:
            daemon = client.send({"op": "ping"})
        except (OSError, ValueError):
            daemon = None
        state = {**vars(cfg), "daemon": daemon or "not running"}
        print(json.dumps(state, indent=2))
        return 0

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
        from keryx import version

        try:
            # An older daemon would ignore `voice` and play every line in one voice.
            client.current({"op": "ping", "version": version()})
            for n, spec in enumerate(catalogue(cfg.voice)[:count], 1):
                text = f"Voice {n}, {spec.spoken()}."
                request = {"op": "say", "kind": "notice", "text": text, "voice": spec.label()}
                reply = client.send_or_spawn(request)
                if not reply.get("ok"):
                    print(f"{spec.label()}: {reply.get('error')}", file=sys.stderr)
        except (OSError, ValueError) as exc:
            print(f"the keryx daemon did not answer: {exc}", file=sys.stderr)
            return 1
        return 0

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
        from keryx import daemon

        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr
        )
        return 0 if daemon.serve(cfg) else client.LOCK_BUSY_EXIT

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
