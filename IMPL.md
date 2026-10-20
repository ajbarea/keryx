# IMPL

## Current: speaking signal (0.9.2)

keryx writes `speaking.json` into klepsydra's fleet folder while a clip plays (ajbarea/klepsydra#33).
Contract: `docs/speaking-signal.md`.

✅ Done
- `src/keryx/speaking.py`: `envelope` (20 Hz RMS, peak-normalised, 2 decimals), `fleet_dir` (mirrors
  `hooks/klepsydra-fleet.sh`), `SpeakingSignal` (temp file + `os.replace` on one worker thread).
- `Speaker` takes `signal=`: each clip writes at play start; a cut-off clip removes its own file; quiet
  and `close` remove it. `speaking_signal` setting (default on; folder absent writes nothing).
- Tests in `tests/test_speaking.py`, `tests/test_config.py`; docs page, nav, README and config rows.
- Version 0.9.2 in `plugin.json`, `pyproject.toml`, `uv.lock`.

📋 Next
- klepsydra wall side: read the file, match card on `claude_pid` + `claude_start`, draw the waves.

## Install state

- Installed from the `techne` marketplace (`ajbarea/techne`); this repo has no
  marketplace of its own. To test local changes, start a session with
  `claude --plugin-dir .` from this clone.
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".

The long view lives in `ROADMAP.md`.
