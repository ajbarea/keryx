# IMPL

## Current: replay, pronunciations, loudness

`loudness.py` levels each sentence to -16 LUFS with a peak limiter; `pronounce.py` rewrites
listed words before synthesis; `bin/keryx-replay` is a synchronous prompt hook that answers
"say that again" from the speaker's per-terminal last line. Version 0.4.0.

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
