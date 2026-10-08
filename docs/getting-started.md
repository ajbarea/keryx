---
title: Getting started
description: Requirements, install and first run of keryx.
---

# Getting started

## Requirements

- Windows 11 with WSL2. Playback uses `powershell.exe`.
- [uv](https://docs.astral.sh/uv/).
- [Ollama](https://ollama.com), with the summarizer model pulled.
- Claude Code 2.1.287 or later for the `/keryx` command. On an older version the plugin still
  speaks, and you control it from a shell.
- Optional: an NVIDIA GPU. Without one, Kokoro runs on the CPU.

The first run downloads the Kokoro model files (about 350 MB). With an NVIDIA GPU it also
downloads the CUDA runtime wheels (about 2 GB).

While it runs, keryx holds about 4.4 GB of GPU memory: 3.7 GB for the summarizer and 0.7 GB
for Kokoro, measured on an 8 GB card.

## Install

Pull the summarizer model:

```bash
ollama pull gemma3:4b
```

Add the techne marketplace and install the plugin:

```bash
claude plugin marketplace add ajbarea/techne
claude plugin install keryx@techne
```

Restart Claude Code.

## First run

The first prompt after install builds the environment and downloads the models, so the first
reply can take several minutes to be spoken. Later replies start speaking in about 1 to 2
seconds.

Check that the daemon is up:

```bash
keryx status
```

`status` prints the settings as JSON and a `daemon` field that reads `not running` until a
prompt has started it. Say something aloud from a shell to hear the voice:

```bash
keryx say "keryx is working"
```

## Try local changes

This repo is not its own marketplace. To run a checkout, start Claude Code with
`claude --plugin-dir .` from the clone. The plugin cache is keyed by version, so after
changing code, bump `version` in `.claude-plugin/plugin.json` and `pyproject.toml`, or run
`claude plugin uninstall` then `install`.

## Turn it off before a long local-LLM run

Ollama sizes GPU offload when a model loads, so a large model loaded beside keryx can end up
partly on the CPU. Run `/keryx off` first. It shuts the daemon down and unloads the
summarizer, which frees about 4.4 GB of VRAM.
