# IMPL: #95 reserved voices (PR #99) - PARKED 11-23 for the Personal 5h reset

Branch fix/reserved-voices-95 (agy's; Opus agy-review-k r1 fixes committed here).
Push: `git push origin fix/reserved-voices-95:fix/reserved-voices-95`. Never push to main.

## Done (Opus r1)
- Not wired: nothing set reserved_voices (AJ's config lacks it), so the option was dead.
  Added `keryx reserve [VOICE ...] | --none` (names resolved against the stock list; refuses an
  unknown voice), docs/commands.md, README + configuration rows.
- default() rewritten through _is_reserved (agy duplicated the check); dead home-recording guard
  removed (reachable only when every voice is reserved); wrap-around test added.
- Mutations: home, first_free, holderless, wrap-around guards each turn a test red.
- ruff, ty clean; pytest 721 passed + new CLI/voices tests; AJ's ~/.config/keryx unchanged.

## Next
1. Independent Opus reader round (none run yet on this PR).
2. Wiring on the fleet side: klepsydra should run `keryx reserve am_michael bf_emma` (voices.sh
   apply or fleet install) when keryx has `reserve`: open a klepsydra issue + PR.
3. After 0.13.0 (#102) lands: run `keryx reserve am_michael bf_emma`, `keryx off; keryx on`, and
   check a new worker's voice in voices.json is not am_michael/bf_emma (live proof).
