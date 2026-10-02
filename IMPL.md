# IMPL

## Current: a voice per session

`voices.py` hands each session a voice from a graded pool, keyed by repo in
`~/.cache/keryx/voices.json`, with same-gender blends past the pool. The speaker asks it per
utterance; `keryx voices` auditions the pool. Version 0.2.0. Next: duck Spotify while
speaking, prototyped through Core Audio's per-app volume from PowerShell.

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
