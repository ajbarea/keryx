# IMPL

## Current: kourai voices first (0.9.1)

The rotation hands out the ten voices that have kourai character portraits on klepsydra's
fleet wall before any other voice, so a fleet's first ten sessions always show a portrait.

✅ Done
- `POOL` in `src/keryx/voices.py` leads with the ten kourai voices (Cupid `af_heart`,
  Hephaestus `am_michael`, Techne `bf_emma`, Puck `am_puck`, Kallos `af_bella`, Mneme
  `bf_isabella`, Dokimasia `af_aoede`, Aidos `af_kore`, Metis `af_sarah`, Aletheia `af_nova`),
  then `bm_george`, `am_fenrir`, `bm_fable`, `af_alloy`. Accent and gender alternate where the
  set allows, best grade first.
- `SPECIALTY` and the blend logic are unchanged.
- Holds are stored by label, so a reordered pool keeps each terminal's voice.
- `tests/test_voices.py` asserts the exact `POOL` order and that the first ten are the kourai set.
- Version 0.9.1 in `.claude-plugin/plugin.json`, `pyproject.toml` and `uv.lock`.
- Verified: `make lint` clean, `make test` 472 passed.

📋 Next
- AJ's live check: after `claude plugin update`, new sessions get kourai faces on klepsydra's
  fleet wall.

## Install state

- Installed from the `techne` marketplace (`ajbarea/techne`); this repo has no
  marketplace of its own. To test local changes, start a session with
  `claude --plugin-dir .` from this clone.
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".

The long view lives in `ROADMAP.md`.
