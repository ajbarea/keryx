---
title: Troubleshooting
description: What to check when keryx is silent, slow or speaking the wrong thing.
---

# Troubleshooting

The daemon logs to `~/.local/state/keryx/log/daemon.log`, one JSON object per line. Check it first:
`grep '"level": "ERROR"' ~/.local/state/keryx/log/daemon.log` lists the failures, and each
request line names the Claude Code session that sent it (`session=<id>`).

## keryx says it needs uv

`bin/keryx` runs through uv. Install it with `curl -LsSf https://astral.sh/uv/install.sh | sh`, open a new terminal, and run the command again.

## `keryx status` ends with `result: missing`

Each `missing` line names the check and the command that fixes it. The [setup runbook](https://github.com/ajbarea/keryx/blob/main/AGENTS.md) explains each one.

## keryx is silent

Open `daemon.log` and look for `mci error 326`. The README documents it, and the player test
skips on it. It means Windows has no audio output device,
for example because the speakers are off. Nothing needs restarting. The next reply plays once
a device is back.

Other things that silence keryx:

- uv is missing. Run `/keryx status`, which says so and prints the installer.
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

## Ollama server memory

Ollama keeps each loaded model's KV cache in f16 by default. Storing it as q8_0 shrinks it, and
keryx's `keryx status` prints `optional ollama-memory` with the fix until the server has that
setting. Measured with gemma3:4b on Ollama 0.35.0, one 3000-character reply, same model and
prompt, on a throwaway server:

| Server env | GPU over baseline | llama-server RSS | runner flags |
| --- | --- | --- | --- |
| default (f16 KV, flash attention auto) | 3800 MiB | 1161 MB | `-c 4096 --flash-attn auto` |
| `OLLAMA_KV_CACHE_TYPE=q8_0` and `OLLAMA_FLASH_ATTENTION=1` | 3687 MiB | 1088 MB | `--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on` |

That is 113 MiB of GPU memory and 73 MB of RSS saved per loaded gemma3:4b at keryx's 4096
context. Models other tools run at larger contexts save more, because the KV cache grows with
context. Applying it needs sudo, so run it yourself:

```
sudo systemctl edit ollama
# in the editor, add:
[Service]
Environment="OLLAMA_KV_CACHE_TYPE=q8_0"
Environment="OLLAMA_FLASH_ATTENTION=1"
# then
sudo systemctl restart ollama
```

Restarting Ollama unloads every model, so do it between runs. The KV cache type is global: it
applies to every model on that server, including other local runs. A quantized KV cache needs
flash attention, and `OLLAMA_FLASH_ATTENTION=1` forces it on; with `OLLAMA_FLASH_ATTENTION=0` and a quantized cache no model loads, and `keryx status` marks that `missing`. Settings in an `EnvironmentFile=` count too, when keryx can read the file. `keryx status` judges only a running local `ollama` unit, so a server on another host reads `n/a`. keryx sends its own `keep_alive`
with each request, so `OLLAMA_KEEP_ALIVE` only changes other clients. The Windows Ollama app
takes these settings as user environment variables instead. `keryx status` also lists the
loaded models with their context and GPU memory on the `ollama-loaded` line. See the
[Ollama FAQ](https://docs.ollama.com/faq).

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
