# IMPL

## Current: Faithfulness and attribution rules in spoken summaries (#70)

Slice: Prevent spoken summaries from misstating who did what, turning offers into done actions, claiming removed items as updated, or claiming user drafts as assistant acts. Add strict prompt rules, deterministic faithfulness verification with single retry/fallback, real evaluation pairs in `eval/pairs.json`, and an evaluation script in `eval/eval_pairs.py`.

✅ Done
- `src/keryx/summarize.py`:
  - Strengthened `SYSTEM_PROMPT` to enforce: lead with main outcome/decision, preserve attribution ('I' assistant vs 'you' developer), keep offers/questions as questions, claim work done only where explicitly marked done, treat dropped/removed items as not done, and introduce user drafts as "here is a draft for you to send".
  - Updated `EXAMPLES` with concise coverage of removed items, user drafts, pending operations, and offers.
  - Implemented `check_faithfulness(summary, source)` and `is_faithful(summary, source)` checking the 5 failure classes: `question_as_action`, `removed_item_as_done`, `draft_claimed_by_assistant`, `attribution_flip`, and `pending_claimed_as_done`.
  - Added faithfulness verification in `spoken()` with a single guided retry before falling back to opening sentences.
- `eval/pairs.json` & `eval/eval_pairs.py`:
  - Added real failure/faithful test pairs and static/model evaluation harness.
- `tests/test_summarize.py`:
  - Added test cases covering each faithfulness failure category and verify `spoken()` retry and fallback behavior (44 passed).

📋 Next
- Push branch `fix/summary-attribution-70` and open PR with label `bug` and assignee `ajbarea`.
- Run Elenchus review against diff.
- Proceed to next open issue / deliverable.

## Verify
- `uv run ruff check .`: clean (0 errors).
- `uv run ruff format --check .`: clean (62 files formatted).
- `uv run ty check`: clean (0 errors).
- `uv run pytest`: 718 passed in 45.3s.
- `uv run python eval/eval_pairs.py`: 6/6 static pairs passed.
