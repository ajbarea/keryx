---
title: Commands
description: The /keryx command, replaying a line, voices and pronunciations.
---

# Commands

## `/keryx`

| Command | What it does |
| --- | --- |
| `/keryx off` | Stops speech, shuts the daemon down and unloads the summarizer, freeing about 4.4 GB of VRAM |
| `/keryx on` | Turns speech back on; the next prompt starts the daemon |
| `/keryx status` | Shows the settings and whether the daemon is running |
| `/keryx again` | Says this terminal's last line again |
| `/keryx:pronounce` | Teaches keryx how to say a word |

`/keryx` is a [mod](https://code.claude.com/docs/en/plugins/mods/overview) command, available
from Claude Code 2.1.287. It runs at once, without a Claude turn, even while Claude is working.
On an older Claude Code it is an unknown command. Run `keryx on`, `off`, `again` or `status` in
a shell instead.

`on` and `off` write only the `enabled` key to `config.json`. If `KERYX_ENABLED` is set in the
environment, it overrides the file, and keryx prints a note saying so.

## Shell commands

The same `keryx` binary runs from a shell:

| Command | What it does |
| --- | --- |
| `keryx on`, `keryx off` | Turn speech on or off |
| `keryx status` | Show settings and whether the daemon is up |
| `keryx say TEXT` | Speak TEXT as given |
| `keryx again` | Say this terminal's last line again |
| `keryx pronounce [WORD [SAYING]]` | List, forget or set how to say WORD |
| `keryx voices [N]` | Play a line in each of the first N voices in the catalogue (default 8) |
| `keryx stop` | Cut off current speech |
| `keryx daemon` | Run the speech daemon in the foreground |

## Say that again

Typing or dictating "say that again" replays the last line without sending the prompt to
Claude. The phrases the code matches include "say that again", "say it once more", "come
again", "what did you say" and "I didn't catch that". The whole prompt must be the request:
"say that again in Spanish" goes to Claude, and so does any prompt over 60 characters.

A replay says only what was heard. The line to replay is the one whose first sentence has
started to play. If nothing has been spoken yet, or no daemon runs, the prompt goes to Claude
as usual.

## Voices

Each terminal speaks in its own voice, through `/clear` and resume too. A repo keeps its voice
across restarts. A second terminal open in the same repo borrows another voice, and once
the stock voices run out, new terminals get blends of two. Set `distinct_voices` to `false` to
speak every terminal in `voice`.

A line starts with the repo's name when it comes from a different repo than the last one.

## Pronunciations

Kokoro gets some words wrong, repo names especially. `keryx pronounce` teaches it.

```bash
keryx pronounce ajsoftworks AJ soft works     # set, then keryx says the word once
keryx pronounce                               # list
keryx pronounce ajsoftworks                   # forget
```

Pronunciations live in `~/.config/keryx/pronounce.json` (under `$XDG_CONFIG_HOME` when set) as
a JSON object of word to saying. A word matches as a whole word, without regard to case,
longest first. The replacement happens in each sentence just before synthesis, so repo names in
announcements are covered. The daemon rereads the file when it changes.

### The `keryx:pronounce` skill

Claude can run `/keryx:pronounce` itself. When you say "ajsoftworks should sound like AJ soft
works", it runs `keryx pronounce` and reports what changed in one line. It also lists and
forgets pronunciations on request.

### Plain words and phonemes

Write how a word should sound as plain words or spelled-out letters: `AJ`, `F L`.

When no spelling can reach a sound, write phonemes between slashes, in espeak's IPA, with the
stress mark before the stressed vowel:

```bash
keryx pronounce techne /tˈexni/
```

espeak reads `techne` as /tˈɛkn/, and no respelling yields the Greek χ. A saying between
slashes keeps the phonemes: the sentence is phonemized around the word and handed to Kokoro as
phonemes. Kokoro's phoneme set has the Greek x, θ, ð, ɣ and ʝ.

Two conveniences apply inside slashes. An ASCII `g` is read as IPA's script g, and an ASCII
`'` as the stress mark, since Kokoro has no token for either look-alike. Commas and colons are
Kokoro's pauses and stay as written.

keryx refuses a symbol Kokoro cannot voice and names it, for example
`Kokoro has no sound for ...; not saved`. A `pronounce.json` that cannot be read as a JSON
object stops `keryx pronounce` with an error rather than overwriting it.
