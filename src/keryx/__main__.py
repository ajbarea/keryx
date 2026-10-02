"""keryx: give Claude Code a voice.

keryx hook             read a Claude Code hook payload on stdin
keryx on | off         turn speech on or off
keryx status           show settings and whether the daemon is up
keryx say TEXT         speak TEXT as given
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

COMMANDS = ("hook", "on", "off", "status", "say", "stop", "daemon")


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
            reply = client.send_or_spawn(request)
            if request["op"] == "warm" and reply.get("version") != request["version"]:
                client.replace_daemon(request, reply)
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
