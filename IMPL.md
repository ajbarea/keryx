# IMPL

## Current: cold-start fix

On the first reply after the daemon's 4-hour idle exit, `gemma3:4b` took 44 s to load from
disk. The 30 s generate timeout hung up, Ollama aborted the load, and the reply fell back to
its opening sentences. This change loads the model under its own timeout before generating,
adds a `warm` op and a `SessionStart` hook that sends it, and moves shortening off the
synth thread so notices never queue behind a load.

Known limit: sessions still running 0.1.0 hooks re-sync the shared venv to the 0.1.0 checkout,
so a daemon may retire and respawn on an old version until those sessions are restarted. Version 0.1.1 so `claude plugin update` picks it up.

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
