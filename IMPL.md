# IMPL

## Current: memory and performance batch (0.10.0, PRs #48 to #52)

✅ Done (merged; numbers are in each PR)
- #44 / #48: `num_ctx` 4096 on warm and chat, and the reply sent to the model is capped at 5600
  chars (its opening and close). 2048 would save only 44 MiB of VRAM.
- #43 / #49: `keep_alive` setting, 5m by default, always sent to Ollama as seconds.
- #46 / #50: Kokoro CUDA `kSameAsRequested` + per-run arena shrinkage: idle 570 MiB (was
  1178), peak 1368. No `gpu_mem_limit`, because one under the need fails mid-sentence.
- #45 / #51: below `min_free_ram_mb` / `min_free_vram_mb` with the model not loaded (or
  loading), the reply is trimmed; `keryx status` shows `last_reply`.
- #47 / #52: `keryx status` reports `ollama-memory` (KV cache, flash attention, keep-alive) and
  `ollama-loaded`.

📋 Next
- AJ: apply the Ollama drop-in in docs/troubleshooting.md#ollama-server-memory (sudo; restarting
  Ollama unloads every model). Measured: 113 MiB less GPU memory and 73 MB less RSS per load.
- AJ: `/keryx on` when ready; the live daemon stayed off for this batch.

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
