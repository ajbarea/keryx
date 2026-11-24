# IMPL

## Current: Session Voice Naming & Immediate Daemon Startup (#73, #89)

Slice: A session names its voice via `KERYX_VOICE` (passed on every request: warm, stop, say, notice), the daemon honours and pins the terminal hold without mutating the repo's home voice, unknown or unavailable voices fall back to rotation gracefully, and `keryx on` immediately warms Kokoro and starts the daemon.

✅ Done
- `src/keryx/hook.py`: Added `requested_voice()` reading `KERYX_VOICE` and attached `"voice"` to `SessionStart` (warm), `UserPromptSubmit` (stop), `Stop` (say), and `Notification` (say) requests.
- `src/keryx/voices.py`: Added `_ensure_spec()` to dynamically index valid, available Kokoro single voices (like `bf_alice`) for holders; updated `assign()` to honour requested voices and keep them pinned across turns and restarts without altering repo home voice; updated blend detection to check `len(names) > 1` rather than index threshold.
- `src/keryx/speaker.py`: Updated `claim()` to pin requested voice for the holder when provided, falling back to rotation `assign()`; updated `submit()` to pin explicit voices for terminal holders.
- `src/keryx/daemon.py`: Updated `claim()` to extract request voice and pass to `speaker.claim()`; updated `op == "say"` to fall back to rotation instead of rejecting session/terminal requests with unknown/unavailable voices.
- `src/keryx/__main__.py`: Added `client.send_or_spawn({"op": "warm"})` when `keryx on` runs so the daemon and Kokoro warm up before the next reply; updated `keryx status` without a running daemon to report `"starts with the next reply"` when enabled and `"not running"` when disabled.
- `tests/`: Added unit tests in `test_hook.py`, `test_voices.py`, `test_daemon.py`, and `test_cli.py` covering session voice naming, fallback to rotation on invalid/unavailable voices, pinning available single voices outside catalogue, and daemon startup on `on` (680 passed, 0 failed).

📋 Next
- Fast-forward merge `feat/session-voice-73-89` to `main` and push to remote.
- Proceed with `klepsydra#389` to align the card character and terminal voice launch.

## Verify
- `ruff check src/ tests/`: clean.
- `ruff format --check src/ tests/`: clean.
- `ty check`: clean (0 errors).
- `pytest`: 680 passed in 26.6s.
