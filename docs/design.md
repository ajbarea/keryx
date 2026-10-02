# Design

Measured on the target workstation, 2026-10-01: Windows 11, WSL2, RTX 3060 Ti (8 GB),
6 cores, Ollama 0.35.0.

## What gets said

Each reply becomes one or two spoken sentences: the outcome, then what Claude needs from the
user, if anything. Reading the whole reply was rejected because replies run to thousands of
characters of tables and paths. Speaking only on permission prompts was rejected because the
point is to follow the conversation without reading it.

## Who writes the spoken line

| Option | Cost | Latency | Result |
| --- | --- | --- | --- |
| Local Ollama model | free | about 1 s warm | chosen |
| Claude writes a spoken line in each reply | about 30 output tokens per turn | none | adds a line to every reply on screen |
| Haiku via `claude -p` | plan usage on every turn | 6.2 s and 7.3 s | both test calls answered the reply instead of restating it |

`research(2026-10)`: existing Claude Code TTS plugins use either Haiku through `claude -p`
(kyleoliveiro/claude-speak) or a skill that has Claude call a speak tool
(RedjiJB/claude-voice-mcp); none uses a local model.

## Which model, and the prompt

Twenty end-of-turn replies were drawn from local Claude Code transcripts, spread by length;
17 were long enough to reach the model. Each round, an independent Opus agent scored every
output blind on faithful, useful and speakable (0 to 2 each, 102 maximum per candidate).
Scripts and tallies are in [eval/](../eval/).

- **Round 1**, a system prompt alone, 8 models: the best total was 70 (`qwen3:1.7b`). The
  main failure was invented requests. `qwen3:4b` scored 0 because its reasoning leaked into
  the output despite `think: false`.
- **Round 2**, the task framed as a rewrite with three worked examples: `gemma4:e2b` 79,
  `gemma3:4b` 75. One example's wording leaked into unrelated outputs, and pending work was
  described as done.
- **Round 3**, a rule to keep pending work pending, and two examples with unrelated
  subjects: `gemma3:4b` 76 with 1 unfaithful line of 17, `gemma4:e2b` 76 with 3.

`gemma3:4b` with the round-3 prompt ships. The totals tie, and faithfulness decides: saying
something false aloud costs more than an awkward phrase. It takes a median 1.06 s per reply
and 3.7 GB of VRAM measured with `nvidia-smi` (Ollama reported 2.88 GB).

`research(2026-10)`: small-model candidates were taken from current Ollama roundups (Gemma 3
and 4, Qwen 3 and 3.5, Llama 3.2).

## Text to speech

Kokoro-82M through `kokoro-onnx` 0.6.1 (released 2026-08). The official `kokoro` package was
rejected: last release April 2025, Python below 3.13, and it pulls PyTorch.

| Runtime | First sentence (4.4 s of audio) |
| --- | --- |
| ONNX Runtime, CPU, fp32 | 2.70 to 2.92 s |
| ONNX Runtime, CUDA | 0.19 to 0.37 s |

The int8 model was slower than fp32 on this CPU: 11.9 to 16.0 s against 3.0 to 4.9 s for a
7.6 s line, both measured while model downloads were running.

CUDA ships as the `cuda` extra (about 2 GB of NVIDIA wheels); `onnxruntime-gpu` replaces
kokoro-onnx's CPU-only `onnxruntime` through a uv override, and falls back to its CPU
provider when the CUDA libraries are missing. Synthesis runs one sentence ahead of playback.

## Playback

WSLg's PulseAudio sink was tried first. One `paplay` call returned in 186 ms for a 0.5 s
clip, too fast to have played it, and the next hung for 30 s with "Failed to drain stream:
Timeout" ([microsoft/wslg#1392](https://github.com/microsoft/wslg/issues/1392)).

PowerShell's `System.Media.SoundPlayer` plays reliably. A fresh `powershell.exe` costs 309 to
444 ms, so one process stays open and takes `play` and `stop` lines on stdin; after the first
clip, each play adds about 6 ms. The WAV must sit on a Windows drive: loading from a
`\\wsl.localhost` path took 10 to 12 s and logged vsock errors.

## Process model

- **Hooks** are `async`, so Claude Code never waits on them. `Stop` sends the reply.
  `Notification` sends permission and elicitation prompts. `UserPromptSubmit` stops that
  session's speech, starts the daemon if needed, and preloads the summarizer, since a reply
  is coming.
- **One daemon per machine** on a Unix socket, guarded by a lock file so a second daemon
  exits instead of taking over the socket.
- **One queue** serves every session. A new prompt cancels only that session's speech.
- **Cold start.** Loading `gemma3:4b` took 14 s on a quiet GPU and up to 34 s while models
  were downloading. The model stays loaded 30 minutes after its last use, and the preload on
  each prompt hides the load behind Claude's own working time.
- **Headless sessions** (`claude -p` and the SDK, whose `CLAUDE_CODE_ENTRYPOINT` starts
  with `sdk`) stay silent.
- **Late replies.** Hooks run async, so a reply's hook can land after the next prompt's.
  Each request carries its `prompt_id`, and the daemon drops a reply from an older prompt
  than the session's latest.
- **Off frees the GPU**: `/keryx:off` shuts the daemon down and unloads the summarizer,
  freeing 4,464 MiB measured (3,791 for `gemma3:4b`, the rest Kokoro).
  With two summarizer models and Kokoro loaded, the GPU sat at 7.6 of 8 GB and one reply took
  4.98 s instead of about 1 s.
