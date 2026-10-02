# IMPL

## Current: ducking other apps while speaking

`ducker.cs` lowers listed apps' per-app volume through Core Audio from the player's
PowerShell process, with a state file so a crash cannot leave the music down; the speaker
ducks once per run of speech and restores after 1 s of quiet. Version 0.3.0.

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
