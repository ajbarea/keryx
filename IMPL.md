# IMPL

## Current: 0.11.0 released (PRs #59 to #61)

✅ Done
- #61: each session's latest spoken reply kept as `replies/<session>.wav` beside klepsydra's
  `fleet/` (klepsydra #100's play buttons); `reply_clips` on by default.
- #60: af_aoede (Dokimasia) handed out last of the ten portrait voices.
- #59: onnxruntime-gpu 1.31; CUDA load and synthesis checked on AJ's GPU.

📋 Next
- After install: tap a reply clip on klepsydra's iPhone wall once.

## Verify
- `make lint`; `uv run pytest -q` (`test_the_real_powershell_loop_plays_a_clip_to_its_end`
  drives real Windows audio and fails intermittently on main too).
- A worktree's `uv sync` leaves out the `cuda` extra, so Kokoro there falls back to the CPU.
  Measure GPU numbers with main's venv (`bin/keryx` adds `--extra cuda` when nvidia-smi exists).

## Install state

- Installed from the `techne` marketplace (`ajbarea/techne`); this repo has no
  marketplace of its own. To test local changes, start a session with
  `claude --plugin-dir .` from this clone.
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".

The long view lives in `ROADMAP.md`.
