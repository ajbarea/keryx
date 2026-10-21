# IMPL

## Current: Hesychia last among single voices (0.9.4, PR #42)

`af_nicole` (Hesychia) reached about the 5th terminal: `_first_free` avoided homed voices over all
singles at once, and she is nobody's home.

✅ Done
- `_first_free(taken, now, below)`: pool singles (unhomed, then an idle repo's home), then
  `af_nicole`, then blends; None when nothing is free.
- Only new hand-outs follow this: a terminal or repo already on her (pinned or not) keeps her.
- Tests: a borrowed pool voice beats her; she comes when all 14 pool voices are held.

📋 Next
- Merge, deploy (pull main, `claude plugin update keryx@techne`, `{"op":"quit"}` on the
  socket), `keryx status`.

## Verify
- `make lint`; `uv run pytest -q` (`test_the_real_powershell_loop_plays_a_clip_to_its_end`
  drives real Windows audio and fails intermittently on main too).

## Install state

- Installed from the `techne` marketplace (`ajbarea/techne`); this repo has no
  marketplace of its own. To test local changes, start a session with
  `claude --plugin-dir .` from this clone.
- The plugin cache is keyed by version: after changing code, bump `version` in
  `.claude-plugin/plugin.json` and `pyproject.toml`, or `claude plugin uninstall` then
  `install`, or `claude plugin update` reports "already at the latest version".

The long view lives in `ROADMAP.md`.
