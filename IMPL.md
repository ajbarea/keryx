# IMPL

## Current: Dual-Runtime Compatibility for AGY (#83)

Slice: Complete cross-runtime parity for Google Antigravity (AGY) in Keryx:
1. Update `skills/pronounce/SKILL.md` to be tool-agnostic (supporting `run_command` in AGY and `Bash` in Claude Code) and eliminate Claude Code-specific `!` backtick dynamic interpolation in favor of clear execution runbooks.
2. Intercept replay requests in `PreInvocation` hook for AGY sessions, send `op: again` to the daemon, and return an AGY termination payload with user markdown, preventing prompt tokens from reaching the model.

✅ Done
- `skills/pronounce/SKILL.md`: Added `name: pronounce`, updated `allowed-tools` to include `run_command`, replaced `!` backtick command interpolation with direct procedural steps.
- `src/keryx/hook.py`: Updated `normalize()` to tag `out["engine"] = "agy"` when `hookEventName` is present.
- `src/keryx/__main__.py`: Added AGY `PreInvocation` replay interception in `cmd == "hook"`, calling `client.send({"op": "again", ...})` and emitting `{"terminationBehavior": "terminate", "injectSteps": [...]}`.
- `tests/test_cli.py`: Added tests covering AGY `PreInvocation` replay phrase termination and fallback when not replayed.

📋 Next
- Push branch `feat/agy-dual-runtime-compat`.
- Open PR and self-review.

## Verify
- `ruff check`: clean.
- `ruff format --check`: clean.
- `ty check`: clean.
- `pytest`: 712 passed in 36.2s.
