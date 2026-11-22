---
name: pronounce
description: Teach keryx how to say a word it mispronounces, like a repo name. Use when the user says a word should sound like something else ("ajsoftworks should sound like AJ soft works", "pronounce X as Y", "say X like Y"), or asks to list or forget pronunciations.
allowed-tools: Bash(keryx pronounce:*), run_command
---

Pronunciations so far:

!`keryx pronounce`

In environments where backticks are not pre-evaluated (such as Antigravity), run `keryx pronounce` via `run_command` to list current pronunciations.

To set one, run `keryx pronounce "<word>" <how it should sound>`, for example
`keryx pronounce ajsoftworks AJ soft works`; keryx then says the word once so the user
hears it. To forget one, run `keryx pronounce "<word>"` with nothing after it. Write how it
should sound as plain words or spelled-out letters (`AJ`, `F L`). Only when no spelling can
reach a sound, such as the Greek χ in `techne`, write phonemes between slashes in espeak's
IPA, with the stress mark before the stressed vowel: `keryx pronounce techne /tˈexni/`.
keryx refuses a symbol Kokoro cannot voice and names it.
Report what changed in one line.
