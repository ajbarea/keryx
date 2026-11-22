# IMPL

## Current: Status Polish & Onboarding Follow-ups (#25)

Slice: When Ollama is installed on Windows but stopped, suggest starting the Ollama app in Windows (avoiding duplicate WSL installs when `ollama.exe` exists on PATH); name the source of non-Windows audio_dir values and provide persistent fixes; align `/keryx status` usage description with `keryx status` CLI; clarify in getting-started docs that `keryx status` checks host requirements rather than the Claude Code version.

✅ Done
- `src/keryx/doctor.py`: Added check for `which("ollama.exe")` to recommend `"fix: start the Ollama app in Windows"`. Added source identification for bad `audio_dir` (environment variable vs config file) and persistent fix instructions.
- `hooks/register.ts`: Updated `/keryx status` usage description to `'show settings, daemon state and setup checks'`.
- `docs/getting-started.md`: Clarified that `keryx status` checks host requirements (uv, PowerShell, Ollama, model, Windows audio dir) and does not check the Claude Code version.
- `tests/test_doctor.py`: Added tests covering `ollama.exe` detection when Ollama is stopped and audio_dir source/fix attribution.

📋 Next
- Push branch `fix/status-polish-25` to origin.
- Open PR for issue #25.
- Self-review against elenchus bug-class catalog.

## Verify
- `ruff check`: clean.
- `ruff format --check`: clean.
- `ty check`: clean.
- `pytest`: 711 passed in 35.0s.
- `docs-build`: clean.
