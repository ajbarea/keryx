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

## Voices

Each terminal gets its own voice so parallel terminals are told apart by ear; the repo name
is still spoken when the speaker changes. The pool is Kokoro v1.0's English voices graded C
or better in its VOICES.md, 15 of 28, ordered so neighbours differ in accent or gender, best
grades first. British voices are phonemized as `en-gb`, and a blend in the accent of the
voice it weighs most. Past the pool come same-gender blends (the weighted mean of two
voices' style vectors) at 50/50, 70/30 and 30/70; blends across genders are reported to come
out muddy. All eight first voices and three blends were told apart by ear on 2026-10-02.

A terminal is its Claude Code process: the hook's nearest ancestor named `claude`, as
`pid:starttime` so a reused pid is not mistaken for it. Session ids would not do: `/clear`
and resume start new sessions in the same terminal, and `SessionEnd` gets a 1.5 s budget at
exit and may not run at all when a terminal is killed. A terminal holds its voice while its
process runs, which the daemon reads from `/proc`; a hook outside Claude Code (no such
ancestor) holds by session id and lapses 4 hours after its last prompt or reply.

A repo keeps the voice it was first given, stored by label in `~/.cache/keryx/voices.json`.
A terminal takes its repo's voice unless another terminal holds it; then it borrows the
first voice that no repo heard in the last 14 days calls home and nobody holds. Voices are
claimed on `SessionStart` and on each prompt, before the first reply. Holds are saved with
wall-clock times, so a daemon restart does not let two terminals trade voices; a clock that
jumps back counts from the jump. A line with no session (`keryx say`) takes a voice nobody
holds, so it is not mistaken for a terminal's. Repos unheard for 90 days are dropped from
the file. The repo name comes from `.git` read directly (a worktree's `commondir` leads to
its main checkout), so a prompt's stop never waits on a `git` subprocess. Hashing
repo names to voices was rejected: with 15 voices, two of six repos already share one about
two times in three. Claude Code does not report how many sessions are open, so the daemon
counts the ones it has heard from.

## Playback

WSLg's PulseAudio sink was tried first. One `paplay` call returned in 186 ms for a 0.5 s
clip, too fast to have played it, and the next hung for 30 s with "Failed to drain stream:
Timeout" ([microsoft/wslg#1392](https://github.com/microsoft/wslg/issues/1392)).

PowerShell plays reliably. A fresh `powershell.exe` costs 309 to 444 ms, so one process
stays open and takes `play`, `mode` and `stop` lines on stdin; after the first clip, each play
adds about 30 ms (MCI's close, open and play, measured 29 to 32 ms). The WAV must sit on a Windows drive: loading from a `\\wsl.localhost` path
took 10 to 12 s and logged vsock errors.

Playback first used `System.Media.SoundPlayer.Play()` and waited the clip's length before the
next `play`, which began with `Stop()`. Sentences then ran together now and then (2026-10-03):
Kokoro ends a sentence with only 59 to 127 ms of silence, and through MCI a 5.10 s clip took
5.22 s from `play` to stopped, so a late start ate the pause. `PlaySync` on a worker thread
reports the end but cannot be stopped from another thread. MCI (`mciSendString`) can do
both, so the loop plays through MCI and the daemon asks `mode` from 0.25 s before a clip's
end until it reads `stopped`.

## Loudness

Kokoro's sentences measured -19.1 to -23.2 LUFS across the first four voices (2026-10-02),
so speech sat under music that Spotify plays at about -14 LUFS and one voice sounded louder
than the next. Each sentence is now brought to -16 LUFS (ITU-R BS.1770 through pyloudnorm
0.2.0), in the -16 to -18 LUFS range used for speech, and a lookahead limiter keeps its
sample peaks under -1.5 dBFS, half a dB inside the usual -1 dBTP true-peak limit. Measured on
the same sentences afterwards: -16.0 to -16.9 LUFS with peaks at or below -1.5 dBFS. Against
Spotify ducked to a quarter (about -26 LUFS) that puts speech about 10 LU above the music.
A clip shorter than BS.1770's 0.4 s gating block is padded with silence to measure it, and
the reading is raised by 10 log10(block / length) to undo the padding's dilution: without
that, a 0.2 s tone read 3 dB quieter than the same tone at 1 s and came out 3 dB too loud.

## Saying it again, and pronunciations

"Say that again" is caught before it reaches Claude, by the one synchronous hook: every prompt
waits on it, so a shell screen turns away anything that is not a short prompt naming "again",
"repeat", "pardon", "catch", "hear" or "what did you", measured at 8 ms, and only then starts
Python, 0.17 s for a real replay. Python matches the whole prompt against a strict pattern,
so "say that again in Spanish" still goes to Claude, then asks the daemon to say the
terminal's last line again in the same voice and blocks the prompt. With nothing to replay
(no daemon, or nothing said yet) the prompt goes to Claude, which can answer it itself. The
asynchronous prompt hook still records these prompts, so Claude's answer is not dropped as
stale, but without stopping speech, which would cut the replay off. A replay cuts off what
that session is saying now and keeps a reply still with the summarizer. `keryx again` from a
shell outside Claude Code has no terminal to look up and says the newest line.

Pronunciations live in `~/.config/keryx/pronounce.json` and replace whole words, without
regard to case and longest first, in each sentence just before synthesis, so repo names in
announcements are covered too. The daemon rereads the file when it changes. The
`/keryx:pronounce` skill is the one Claude may invoke on its own, so "ajsoftworks should
sound like AJ soft works" works in plain words.

A saying between slashes is phonemes, for sounds no English spelling reaches. espeak reads
`techne` as /tˈɛkn/ and no respelling yields the Greek χ, so `keryx pronounce techne
/tˈexni/` keeps the phonemes: the sentence is phonemized around the word and handed to
Kokoro as phonemes. Kokoro's phoneme set has the Greek x, θ, ð, ɣ and ʝ.

## Ducking

While keryx speaks, other apps (Spotify by default) drop to a quarter of their volume, then
come back. Three ways were weighed:

- **Per-app volume** through Core Audio: each app's audio session exposes
  `ISimpleAudioVolume`. Chosen: local, instant, and it changes only that app's level.
- **Pause and resume** through Windows' media session API
  (`GlobalSystemMediaTransportControlsSession.TryPauseAsync`). Rejected: stopping the music
  for every few-second gist is jarring, and it would also resume music the user paused.
- **Spotify's Web API**: needs Premium, OAuth and the network, and covers one app.

The player's PowerShell process compiles `ducker.cs` once at start and takes `duck` and
`unduck` lines like `play` (the compile adds about 0.18 s to a player's start: 0.37 to 0.40 s
against 0.19 to 0.21 s). A duck covers every active output device and writes each audio
session's instance id, original and lowered volume to `keryx-ducked.txt` before it changes
anything; an unduck restores a session only if its
volume is still the lowered one, so a level changed by hand meanwhile is kept. A new player
restores anything that file still records, and the loop restores again when its stdin
closes, so a crash cannot leave the music down; a player restarted mid-speech ducks again. The speaker ducks before the first clip of a
run of speech and restores after 1 s with nothing queued, being synthesized or playing; a
reply still waiting on the summarizer does not hold the music down.

Measured live on 2026-10-02 with Spotify playing: the volume read 0.25 for all of a
three-sentence line and returned to 1 about a second after it. With the daemon killed by
SIGKILL mid-line the volume was back to 1 within 3 s; with the player killed, the next
unduck started a new player that restored it 3.1 s later. AJ confirmed the 25% level by ear.

## Process model

- **Hooks** are `async`, so Claude Code never waits on them. With a hook that sleeps 15 s on
  `SessionStart`, the first response of `claude -p --model haiku` came at a median 9.0 s
  (7.5-9.8) run async, 23.3 s (21.3-23.8) run sync, and 6.4 s (6.4-9.7) with no hook; three
  runs each, 2026-10-02. `SessionStart` starts the daemon if needed and preloads the
  summarizer. A daemon from another keryx version (0.1.0 has no `warm` op) is retired and
  replaced with the current code. `Stop` sends the reply. `Notification` sends permission
  and elicitation prompts. `UserPromptSubmit` stops that session's speech, starts the daemon if needed, and
  preloads the summarizer, since a reply is coming.
- **One daemon per machine** on a Unix socket, guarded by a lock file so a second daemon
  exits instead of taking over the socket.
- **One queue** serves every session. A new prompt cancels only that session's speech.
- **Cold start.** Loading `gemma3:4b` took 4 to 14 s with the model file in the page cache,
  34 s while models were downloading, and 44 s read from disk after a night idle. Ollama
  aborts a load when its client hangs up, so the summarizer loads the model first under a
  120 s timeout, then generates under 30 s. A loaded model answers the load call in about
  10 ms. The model stays loaded 30 minutes after its last use. `SessionStart` and each prompt
  preload it, which puts the load behind the developer's typing and Claude's working time.
  Shortening runs on its own thread, so a permission prompt is spoken while a reply waits
  on a load.
- **Headless sessions** (`claude -p` and the SDK, whose `CLAUDE_CODE_ENTRYPOINT` starts
  with `sdk`) stay silent.
- **Late replies.** Hooks run async, so a reply's hook can land after the next prompt's.
  Each request carries its `prompt_id`, and the daemon drops a reply from an older prompt
  than the session's latest.
- **Off frees the GPU**: `/keryx:off` shuts the daemon down and unloads the summarizer,
  freeing 4,464 MiB measured (3,791 for `gemma3:4b`, the rest Kokoro).
  With two summarizer models and Kokoro loaded, the GPU sat at 7.6 of 8 GB and one reply took
  4.98 s instead of about 1 s.
