"""keryx: give Claude Code a voice.

keryx hook             read a Claude Code hook payload on stdin
keryx replay-hook      the same for the synchronous "say that again" prompt hook
keryx on | off         turn speech on or off
keryx status           show settings and whether the daemon is up
keryx say TEXT         speak TEXT as given
keryx again            say this terminal's last line again
keryx pronounce [WORD [SAYING]]   list, forget (WORD only) or set how to say WORD
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
from keryx.config import Config

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

    if cmd == "hook":
        from keryx import hook

        if not cfg.enabled:
            return 0
        request = hook.request_for(hook.parse(sys.stdin.read()), hook.entrypoint())
        if request is None:
            return 0
        # Spawning on a prompt, not just a reply, loads the voice while Claude works.
        # No daemon to answer (turned off, or it failed to start): nothing to say.
        with contextlib.suppress(OSError):
            if request["op"] == "warm":
                client.current(request)
            else:
                client.send_or_spawn(request)
        return 0

    if cmd in ("on", "off"):
        stored = Config.load(env=False)  # don't persist env overrides into the file
        stored.enabled = cmd == "on"
        stored.save()
        if not stored.enabled:
            # Off frees the GPU: the daemon exits (releasing Kokoro) and the model unloads.
            with contextlib.suppress(OSError):
                client.send({"op": "quit"})
            if cfg.model:
                from keryx.summarize import OllamaClient

                with contextlib.suppress(OSError):
                    OllamaClient(cfg.model, cfg.ollama_host).unload()
        print(f"keryx is {cmd}")
        if Config.load().enabled != stored.enabled:
            print("note: KERYX_ENABLED in the environment overrides this")
        return 0

    if cmd == "status":
        try:
            daemon = client.send({"op": "ping"})
        except OSError:
            daemon = None
        state = {**vars(cfg), "daemon": daemon or "not running"}
        print(json.dumps(state, indent=2))
        return 0

    if cmd == "say":
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
        except OSError as exc:
            print(f"the keryx daemon did not answer: {exc}", file=sys.stderr)
            return 1
        return 0

    if cmd == "replay-hook":
        # Synchronous UserPromptSubmit: "say that again" replays instead of reaching Claude.
        from keryx import hook
        from keryx.procs import terminal_id

        event = hook.parse(sys.stdin.read())
        prompt = str(event.get("prompt") or "")
        if not cfg.enabled or hook.entrypoint().startswith(hook.HEADLESS_PREFIX):
            return 0
        if not hook.is_replay(prompt):
            return 0
        request = {"op": "again", "terminal": terminal_id(), "session": event.get("session_id", "")}
        try:
            replayed = client.send(request).get("replayed")
        except OSError:
            replayed = False  # no daemon, so nothing to replay: let Claude answer
        if replayed:
            print(json.dumps({"decision": "block", "reason": "keryx: saying that again"}))
        return 0

    if cmd == "again":
        from keryx.procs import terminal_id

        try:
            reply = client.send({"op": "again", "terminal": terminal_id()})
        except OSError:
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
