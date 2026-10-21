# IMPL

## Current: every character before any blend (0.9.3, #40, PR #41)

On 10-21 klepsydra showed three letter medallions (blends) while ten character voices sat free:
rotation skipped every single voice that an idle repo calls home before it reused one.

✅ Done
- `catalogue`: pool singles, then `af_nicole`, then blends. `VoiceBook._singles` counts the
  singles at the head of `_specs`.
- `_first_free(taken, now, below)`: pool singles (no one's home, then an idle repo's home), then `af_nicole`,
  then blends; None when nothing is free.
- `assign`: the repo's own voice when it is a free single, else the first free single; a
  terminal on a blend moves at its next line; a repo homed in a blend is rehomed to its single.
- Review round 1: dropped a `pinned` key (`set_voice` cannot pin a blend), home first on a move,
  stale "opt-in" wording, a regression test that fails on the round-1 code.
- Review round 2: a borrowed voice never becomes a second repo's home (a test repo homed on a
  blend would have taken keryx's own voice); the homes in `voices.json` stay unique.
- Docs: README, `docs/commands.md`, `docs/design.md`.

📋 Next
- Merge, deploy (pull main, `claude plugin update keryx@techne`, `{"op":"quit"}` on the
  socket), then check the live wall shows no letter medallions.
- klepsydra still calls Hesychia pin-only (README, `src/fleet-cast.test.js`, portrait briefs):
  fixed in klepsydra's #62 PR.

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
