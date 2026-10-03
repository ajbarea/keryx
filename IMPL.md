# IMPL

## Current: closed-loop playback, phoneme pronunciations

`player.py` plays each WAV through MCI in the long-lived PowerShell loop and asks `mode` near
the clip's end until it stops, so a late start no longer cuts the pause between sentences.
`pronounce.py` passes a `/phonemes/` saying to `voice.py` between ⟦ ⟧ marks, and
`voice.splice` phonemizes the sentence around it for Kokoro. Version 0.5.0.

Next: the code review's remaining findings (one venv shared by every plugin version, CPU
fallback when cuDNN is missing, config coercion and crash-on-bad-file, replay edge cases,
uncapped loudness gain, log rotation).

## Install state

- Installed from the local marketplace (`claude plugin marketplace add ~/ajsoftworks/keryx`).
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".
