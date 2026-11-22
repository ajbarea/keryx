# IMPL

## Current: Duck All Other Apps While Speaking (#71)

Slice: Duck everything by default (`duck_apps: ["*"]`) except keryx's own player PID (`myPid`), support `duck_exclude` (`KERYX_DUCK_EXCLUDE`) for untouched call apps (e.g. Zoom, Teams), lower sessions that start mid-speech and restore with the rest, maintain crash-safe leftover state file restoration, and document Windows Communications ducking vs Core Audio session APIs (`IAudioSessionManager2`, `IAudioSessionEnumerator`, `IAudioSessionControl2`, `ISimpleAudioVolume`).

✅ Done
- `src/keryx/ducker.cs`: Added `myPid` exclusion to skip keryx's own player process; added wildcard `*` support; added `duck_exclude` filtering; added `Duck(string statePath, string appList, float ratio, string excludeList)` overload; added mid-speech session detection reading existing state IDs and appending newly ducked sessions to `statePath`.
- `src/keryx/config.py`: Changed `duck_apps` default to `["*"]`; added `duck_exclude: list[str] = field(default_factory=list)` with environment variable `KERYX_DUCK_EXCLUDE` support.
- `src/keryx/player.py`: Updated `_PS_LOOP` duck handler to parse and pass `duck_exclude` and automatically duck new mid-speech sessions on `play` when ducked; updated `WindowsPlayer.__init__` to accept `duck_exclude` and format duck command.
- `src/keryx/daemon.py`: Passed `duck_exclude=tuple(cfg.duck_exclude)` when instantiating `WindowsPlayer`.
- `src/keryx/speaker.py`: Retained single run ducking lifecycle with mid-speech session lowering delegated to player `play` loop when ducked.
- `docs/configuration.md`, `docs/design.md`, `README.md`: Documented `duck_apps: ["*"]` default, `duck_exclude`, Windows Communications ducking limitations, and cited Core Audio session APIs.
- `tests/test_config.py`, `tests/test_player.py`: Added regression and unit tests for wildcard `*`, `duck_exclude` env/config parsing, process self-exclusion, mid-speech session appending, and leftover state file restoration.

📋 Next
- Run verification (`ruff check`, `ruff format --check`, `ty check`, `pytest`).
- Push branch `feat/duck-all-apps-71` and open PR for `ajbarea/keryx#71`.
- Post Elenchus adversarial review.
- Update desktop log and proceed to `klepsydra#515`.

## Verify
- `ruff check .`: clean.
- `ruff format --check .`: clean.
- `ty check`: clean.
- `pytest`: all tests passing.
