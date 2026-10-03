---
description: Teach keryx how to say a word it mispronounces, like a repo name. Use when the user says a word should sound like something else ("ajsoftworks should sound like AJ soft works", "pronounce X as Y", "say X like Y"), or asks to list or forget pronunciations.
allowed-tools: Bash(keryx pronounce:*)
---

Pronunciations so far:

!`keryx pronounce`

To set one, run `keryx pronounce "<word>" <how it should sound>`, for example
`keryx pronounce ajsoftworks AJ soft works`; keryx then says the word once so the user
hears it. To forget one, run `keryx pronounce "<word>"` with nothing after it. Write how it
should sound as plain words or spelled-out letters (`AJ`, `F L`), not phonetic symbols.
Report what changed in one line.
