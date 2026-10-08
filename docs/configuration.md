---
title: Configuration
description: Every keryx setting, its default and its environment variable.
---

# Configuration

Settings come from `~/.config/keryx/config.json`. Each one can be overridden by an environment
variable named `KERYX_<FIELD>`, such as `KERYX_SPEED=1.3`. The environment wins over the file.

`config.json` holds only what you or `keryx on` and `keryx off` set. A file that cannot be read
is ignored, and `on` and `off` keep it as `config.json.bad`. A value of the wrong type falls
back to the default.

## Settings

| Field | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Speak at all |
| `voice` | `af_heart` | Any [Kokoro voice](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md); the first voice handed out |
| `distinct_voices` | `true` | Give each terminal its own voice; `false` speaks every terminal in `voice` |
| `speed` | `1.0` | Speaking rate |
| `loudness` | `-16.0` | Loudness (LUFS) every sentence is brought to before it plays |
| `model` | `gemma3:4b` | Ollama model that shortens replies; empty to speak the opening sentences instead |
| `ollama_host` | `http://localhost:11434` | Ollama server |
| `duck_apps` | `["Spotify"]` | Windows process names turned down while keryx speaks; `[]` for none |
| `duck_ratio` | `0.25` | The share of their volume ducked apps keep |
| `audio_dir` | `/mnt/c/Windows/Temp/keryx` | Where WAVs are written; must be on a Windows drive |

## Environment variables

| Variable | Effect |
| --- | --- |
| `KERYX_<FIELD>` | Overrides the setting of that name, one variable per field above |
| `XDG_CONFIG_HOME` | Moves the config directory; `config.json` and `pronounce.json` live in `$XDG_CONFIG_HOME/keryx` |
| `XDG_CACHE_HOME` | Moves the cache directory; the daemon socket, `daemon.log`, `voices.json` and the venvs live in `$XDG_CACHE_HOME/keryx` |
| `CLAUDE_CODE_ENTRYPOINT` | Read, not set: a value starting with `sdk` marks a headless session (`claude -p`, the Agent SDK), which keryx keeps silent |

An environment value is read as the type of its field. A boolean is true for `1`, `true`, `yes` and
`on`, and false for anything else. A list such as `duck_apps` is comma-separated:
`KERYX_DUCK_APPS=Spotify,vlc`. A number that does not parse is ignored.

## Files

| Path | Holds |
| --- | --- |
| `~/.config/keryx/config.json` | The settings you changed |
| `~/.config/keryx/pronounce.json` | Pronunciations |
| `~/.cache/keryx/daemon.log` | The daemon's log, readable only by you; one older file of about 1 MB is kept |
| `~/.cache/keryx/voices.json` | Which voice each repo was given |
| `~/.cache/keryx/venv-<version>-<checksum>` | One venv per plugin version and checkout |
| `<audio_dir>` | Spoken WAVs, rotating through 8 slots; deleted when the daemon exits |

Each plugin version runs in its own venv. One whose checkout has been removed is deleted the
next time keryx runs. The unversioned `~/.cache/keryx/venv` from 0.5.0 and earlier is never
deleted by keryx; remove it by hand once no daemon runs from it.

## Ducking

While keryx speaks, apps in `duck_apps` drop to `duck_ratio` of their volume and come back a
second after the last line. A duck covers every active output device. The original volumes are
written to `keryx-ducked.txt` before anything changes, and a restart restores them, so a crash
cannot leave the music down. A level you change by hand during speech is kept.

To duck another app, name its Windows process:

```bash
export KERYX_DUCK_APPS=Spotify,vlc
```

## Choosing a different summarizer

Set `model` to any model Ollama serves, or to the empty string to skip the model and speak the
opening sentences of each reply. The default was chosen over three blind-judged rounds; the
[design record](design.md#which-model-and-the-prompt) has the scores. Two summarizer models
loaded beside Kokoro filled an 8 GB card in that record's measurements.
