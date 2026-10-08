---
title: Troubleshooting
description: What to check when keryx is silent, slow or speaking the wrong thing.
---

# Troubleshooting

The daemon logs to `~/.cache/keryx/daemon.log`. Check it first.

## keryx is silent

Open `daemon.log` and look for `mci error 326`. The README documents it, and the player test
skips on it. It means Windows has no audio output device,
for example because the speakers are off. Nothing needs restarting. The next reply plays once
a device is back.

Other things that silence keryx:

- `/keryx status` shows `"enabled": false`. Run `/keryx on`. If `KERYX_ENABLED` is set in the
  environment, it overrides the file.
- The session is headless (`claude -p` or the Agent SDK). keryx stays silent there on purpose.
- `audio_dir` is not on a Windows drive. Windows can only play from its own drives. A
  `\\wsl.localhost` path loaded in 10 to 12 s in the measurements and logged vsock errors.
- The Windows form of the WAV path (`audio_dir` plus `\keryx-0.wav`) is 128 characters or
  longer. MCI refuses such a path, and the player warns at start.

## The first reply takes minutes

The first prompt after install builds the environment and downloads the Kokoro model files
(about 350 MB) and, with an NVIDIA GPU, the CUDA wheels (about 2 GB). Later replies start
speaking in about 1 to 2 seconds.

## `/keryx` is an unknown command

`/keryx` is a mod command and needs Claude Code 2.1.287 or later. On an older version, run
`keryx on`, `keryx off`, `keryx again` or `keryx status` in a shell.

## Ollama is not reachable

When the summarizer fails or Ollama is down, keryx speaks the opening sentences of the reply
instead of a rewrite. Check that Ollama runs at `ollama_host` and that the model is pulled
(`ollama pull gemma3:4b`).

## A large local model runs partly on the CPU

Ollama sizes GPU offload when a model loads, so a large model loaded beside keryx can end up
partly on the CPU. Run `/keryx off` before a long local-LLM run. It unloads the summarizer and
frees about 4.4 GB of VRAM.

## `config.json` was ignored

keryx ignores a `config.json` it cannot read as a JSON object. `keryx on` and `keryx off` keep
the unreadable file as `config.json.bad` and write a new one.

## `keryx pronounce` refuses a word

`Kokoro has no sound for ...; not saved` means a symbol between slashes is not in Kokoro's
phoneme set. Use another symbol. A `pronounce.json` that cannot be read as a JSON object also
stops the command with an error, so nothing is saved over it. Fix or remove the file.

## Music stays quiet after a crash

keryx writes each ducked app's original volume to `keryx-ducked.txt` in `audio_dir` before it
lowers anything. The next player restores whatever that file records when it starts.
