# Roadmap

Last reviewed: 2026-10-03.

## Possible next steps

- **Lower latency.** Stream the summarizer's tokens and start Kokoro on the first finished
  sentence instead of waiting for the whole line.
- **Spoken subagent results.** `SubagentStop` stays silent today; a long background agent
  finishing may deserve a line.

## Completed

- 2026-10-03: code-review fixes (0.5.1): replay says only what was heard, a venv per plugin
  version, CPU fallback when CUDA will not start, checksummed model files, a bounded private
  log, capped loudness gain, tolerant config.
- 2026-10-03: sentences no longer run together: playback goes through MCI and waits for
  each clip to stop; pronunciations take phonemes (`/tˈexni/`) for sounds English cannot spell.
- 2026-10-02: "say that again", pronunciations, and speech leveled to -16 LUFS.
- 2026-10-02: duck Spotify (or any listed app) while speaking, crash-safe.
- 2026-10-02: a distinct voice per terminal, kept per repo; blends past the stock voices.
- 2026-10-02: cold-start fix. A summarizer load slower than the 30 s generate timeout was
  aborted by Ollama, and the reply fell back to its opening sentences; the model now loads
  under its own 120 s timeout, and `SessionStart` preloads it.
- 2026-10-01: first version. Stop, Notification and UserPromptSubmit hooks; local summarizer
  chosen over three blind-judged rounds; Kokoro on CUDA; Windows playback through a
  persistent PowerShell `SoundPlayer`.
