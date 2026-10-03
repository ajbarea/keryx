# IMPL

## Current: review fixes

Replay says only what was heard. `speaker.py` records a line, and decides whether to announce
its repo, when the line's first sentence starts to play; the repo name is its own clip,
synthesized with the line and played only if the last name heard was another repo's. `again`
cuts only speech that has started, and `stop` also reaches a terminal's speech left under an
older session. A replay prompt holds back its prompt id and the warm-up until the replay
hook finds nothing to replay.

`bin/keryx` runs each plugin version and checkout in its own venv
(`~/.cache/keryx/venv-<version>-<checksum of the path>`) and removes one whose checkout is
gone. Kokoro falls back to the CPU when CUDA will not start, the model files are checked
against pinned SHA-256 sums, `daemon.log` is private and rotates, and `normalize` lifts a
clip by at most 30 dB. Config tolerates a malformed file and `on`/`off` write only `enabled`.
Version 0.5.1.

Not done: the shared `audio_dir`. One daemon serves each user, so it matters only across
users or cache homes, and the ducker's crash recovery relies on a fixed path.

## Install state

- Installed from the `ajsoftworks` marketplace (`ajbarea/ajsoftworks`). To test local
  changes, add this clone as its own marketplace (`claude plugin marketplace add .`) and
  install `keryx@keryx`.
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
