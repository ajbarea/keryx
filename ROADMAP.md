# Roadmap

Last reviewed: 2026-10-02.

## Possible next steps

- **Voice choice.** `af_heart` is Kokoro's default top voice; try others by ear.
- **Lower latency.** Stream the summarizer's tokens and start Kokoro on the first finished
  sentence instead of waiting for the whole line.
- **Spoken subagent results.** `SubagentStop` stays silent today; a long background agent
  finishing may deserve a line.

## Completed

- 2026-10-02: cold-start fix. A summarizer load slower than the 30 s generate timeout was
  aborted by Ollama, and the reply fell back to its opening sentences; the model now loads
  under its own 120 s timeout, and `SessionStart` preloads it.
- 2026-10-01: first version. Stop, Notification and UserPromptSubmit hooks; local summarizer
  chosen over three blind-judged rounds; Kokoro on CUDA; Windows playback through a
  persistent PowerShell `SoundPlayer`.
