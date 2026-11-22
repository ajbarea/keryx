# IMPL

## Current: Reserved Voices in VoiceBook & Daemon (#95)

Slice: A `reserved_voices` option (a list of voice ids) configures voices that keryx will never hand out from the pool or a repo home. A session can only obtain a reserved voice by asking explicitly via `KERYX_VOICE`.

✅ Done
- `src/keryx/config.py`: Added `reserved_voices: list[str] = field(default_factory=list)` to `Config` with env override `KERYX_RESERVED_VOICES`.
- `docs/configuration.md`: Documented `reserved_voices` and its interaction with `KERYX_VOICE`.
- `src/keryx/daemon.py`: Passed `cfg.reserved_voices` to `VoiceBook` in `build_speaker`.
- `src/keryx/voices.py`: Added `reserved` parameter and `_is_reserved()` check in `VoiceBook`. Updated `assign()` and `_first_free()` so reserved voices are never handed out from pool rotation, repo homes (even if previously homed/freed in a reserved voice), or holderless requests, and cannot become a repo's home. Explicit `requested` voice (from `KERYX_VOICE`) still claims the requested voice without homing the repo.
- `tests/test_config.py`: Added unit tests for `reserved_voices` defaults, config loading, and env overrides.
- `tests/test_voices.py`: Added unit tests for pool rotation skipping reserved voices, freed repo home with reserved voice falling back to unreserved pool voice unless asked via `requested`, blends skipping reserved voices, and holderless requests avoiding reserved voices.

📋 Next
- Push branch `fix/reserved-voices-95` to origin.
- Open PR for issue #95 with short top and folded verification details.
- Self-review against elenchus bug-class catalog.

## Verify
- `ruff check`: clean.
- `ruff format --check`: clean.
- `ty check`: clean.
- `pytest`: 720 passed in 41.5s.
