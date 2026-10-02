# Summarizer evaluation

How the summarizer model and prompt were chosen; results in `../docs/design.md`.

```bash
uv run python eval/collect.py                 # 20 replies from local transcripts -> data/
uv run python eval/run.py v3 gemma3:4b ...    # outputs, load time, latency -> data/results-v3.json
uv run python eval/blind.py round3 results-v3.json:gemma3:4b results-v3.json:gemma4:e2b
# a judge agent scores data/blind-round3.json -> data/scores-round3.json (rubric below)
uv run python eval/tally.py round3            # un-blind and total
```

`data/` holds private session text and is gitignored. `tally-*.txt` are the committed totals.
Round 3's candidates are labelled `model|v2` and `model|v3` (prompt versions).

## Judge rubric

Give a fresh agent only the blind file, and tell it not to read the key. For each candidate,
score 0 to 2:

- **faithful**: 2 if every claim is in the reply. 0 if it invents facts or a request, calls
  pending work done, gets who did what wrong, or answers the reply instead of restating it.
- **useful**: 2 if it gives the main outcome and the request when the reply makes one.
- **speakable**: 2 if it is short, natural aloud, and in the first person.
