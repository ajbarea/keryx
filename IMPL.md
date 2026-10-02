# IMPL

## Current: a voice per terminal

`voices.py` hands each terminal a voice from a graded pool, keyed by repo in
`~/.cache/keryx/voices.json`, with same-gender blends past the pool. `procs.py` names a
terminal by its Claude Code process and tells the daemon when it has exited. Voices are
claimed on start and prompt; `keryx voices` auditions the pool. Version 0.2.0. Next: duck Spotify while
speaking, prototyped through Core Audio's per-app volume from PowerShell.

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
