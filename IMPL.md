# IMPL

## Current: Dual-Runtime Compatibility (Claude Code + Antigravity)

Slice: Add native normalization and transcript extraction so keryx speaks for both Claude Code and Antigravity (AGY) sessions without separate forks.

✅ Done
- `src/keryx/hook.py`: Added `last_assistant_message_from_transcript` to extract `PLANNER_RESPONSE` from AGY `transcriptPath` (constant-time tail seek up to 128KB).
- `src/keryx/hook.py`: Added `normalize()` to map `conversationId` -> `session_id`, `hookEventName` -> `hook_event_name`, and `PreInvocation` -> `UserPromptSubmit` (for prompt interruption and replay detection).
- `src/keryx/procs.py`: Added `agy`, `antigravity`, `antigravity-cli` to `CLAUDE_NAMES` so `terminal_id()` detects Antigravity sessions and allocates terminal voices.
- `hooks.json`: Created root hook manifest configuring `SessionStart`, `PreInvocation`, and `Stop`.
- `tests/`: Added unit tests in `test_hook.py` and `test_procs.py` covering AGY `Stop`, `PreInvocation`, `SessionStart`, cancellation, empty transcripts, and `agy` terminal detection (672 passed, 96% coverage).

📋 Next
- Commit changes with conventional commit (`feat(hook): dual-runtime adapter for Claude Code and Antigravity`).
- Document delivery in desktop note.

## Verify
- `make lint`: clean (61 files formatted, ruff checks passed, ty checks passed).
- `make test`: 672 passed, 1 skipped (audio device offline), 96% total coverage.
- Live hook test: verified `bin/keryx hook` handles AGY `SessionStart` and `Stop` payloads without error.
