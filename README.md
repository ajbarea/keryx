# keryx

Gives Claude Code a voice. After each reply, keryx says its gist out loud in one or two
sentences: what happened, and what Claude needs from you. Everything runs locally and costs
no tokens.

## How it works

1. **Hook.** When Claude finishes a turn, the plugin's `Stop` hook sends the reply to a
   background daemon and returns at once.
2. **Shorten.** The daemon strips code, tables and paths. A reply under 200 characters is
   spoken as written; anything longer goes to a local Ollama model (`gemma3:4b`), which
   rewrites it as one or two sentences.
3. **Speak.** Kokoro-82M turns each sentence into audio on the GPU (CPU if there is none),
   one sentence ahead of playback.
4. **Play.** A long-lived PowerShell process plays each WAV on the Windows side.

It also speaks permission prompts ("I need your permission to use Bash"), and stops talking
when you send a new prompt. One daemon serves every Claude session on the machine, so
sessions never talk over each other; a line starts with the repo's name when it comes from a
different repo than the last one.

Audio goes through Windows because WSLg's PulseAudio sink suspends when idle and then drops
or hangs streams ([microsoft/wslg#1392](https://github.com/microsoft/wslg/issues/1392)).
Audio files rotate through 8 slots in `C:\Windows\Temp\keryx` and are deleted when the
daemon exits.

## Requirements

- Windows 11 with WSL2 (playback uses `powershell.exe`)
- [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) with the summarizer
  pulled: `ollama pull gemma3:4b`
- Optional: an NVIDIA GPU. The first run downloads the CUDA runtime wheels (about 2 GB)
  and the Kokoro model files (about 350 MB).

## Install

```bash
claude plugin marketplace add ajbarea/ajsoftworks
claude plugin install keryx@ajsoftworks
```

Then restart Claude Code. The first prompt after install builds the environment and downloads
the models, so the first reply can take several minutes to be spoken; later replies start
speaking in about 1 to 2 seconds.

## Use

| Command | What it does |
| --- | --- |
| `/keryx:off` | Stops speech, shuts the daemon down and unloads the summarizer, freeing about 4.4 GB of VRAM |
| `/keryx:on` | Turns speech back on; the next prompt starts the daemon |
| `/keryx:status` | Shows the settings and whether the daemon is running |
| `/keryx:again` | Says this terminal's last line again |
| `/keryx:pronounce` | Teaches keryx how to say a word; Claude also uses it when you say "X should sound like Y" |

Typing or dictating "say that again" (or "come again?", "I didn't catch that") replays the
last line without sending the prompt to Claude. `keryx pronounce ajsoftworks AJ soft works`
sets a pronunciation from the shell, `keryx pronounce` lists them, and `keryx pronounce WORD`
forgets one; they are kept in `~/.config/keryx/pronounce.json`. A saying between slashes is
phonemes, for sounds English spelling cannot reach: `keryx pronounce techne /tˈexni/`.

Each terminal speaks in its own voice, through `/clear` and resume too. A repo keeps its
voice across terminals and restarts, a second terminal in the same repo gets another, and
once the stock voices run out new terminals get blends of two. `keryx voices [N]` plays the first N voices in the catalogue,
stock voices first.

While keryx speaks, Spotify drops to a quarter of its volume and comes back a second after
the last line; set `duck_apps` to turn down other apps instead.

Turn keryx off before a long local-LLM run: Ollama sizes GPU offload when a model loads, so a
large model loaded beside keryx can end up partly on the CPU.

## Settings

`~/.config/keryx/config.json`, or an environment variable named `KERYX_<FIELD>`:

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

The daemon logs to `~/.cache/keryx/daemon.log`, readable only by you, and keeps one
older file of about 1 MB. Each plugin version runs in its own venv under `~/.cache/keryx/`;
one whose checkout has been removed is deleted the next time keryx runs. The unversioned
`~/.cache/keryx/venv` from 0.5.0 and earlier is never deleted by keryx; remove it by hand
once no daemon runs from it.
`config.json` holds only what you or `keryx on`/`off` set; a file that cannot be read is
ignored, and `on`/`off` keep it as `config.json.bad`.

## Development

```bash
make lint   # ruff format --check, ruff check, ty
make test   # pytest with coverage
```

[docs/design.md](docs/design.md) records the design decisions and the measurements behind
them; [eval/](eval/) holds the summarizer evaluation.

## Why "keryx"

A *keryx* (κῆρυξ) was a herald in ancient Greece: the one who carried a message and
announced it aloud, briefly, to the people it concerned.
