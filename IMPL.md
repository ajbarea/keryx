# IMPL: #70 faithful spoken summaries (PR #103)

Branch fix/summary-attribution-70 (agy's; reworked by Opus agy-review-k 11-23).
Push: `git push origin fix/summary-attribution-70:fix/summary-attribution-70`. Never push to main.

## Done
- agy: prompt rules (who did what, questions stay questions, done only when marked done,
  drafts for you to send, lead with the outcome) + a new few-shot pair; a ~150-line regex
  "faithfulness" checker with a retry; a 6-pair static eval scoring the checker.
- Opus r1, measured on AJ's real replies (233 pairs from daemon.log + transcripts, 11-16..11-23;
  60 sampled, gemma3:4b, a blind A/B reader):

  | | main | this branch (agy) |
  |---|---|---|
  | unfaithful | 24/60 | 23/60 |
  | main point lost | 7 | 5 |
  | pending read as done | 9 | 6 |
  | preferred | 22 | 30 (8 ties) |

  The regex checker flagged 1 of the 233 real summaries: kept out (dead weight; the 6/6 eval
  only scored the checker against pairs written to fit it). The prompt changes are kept.
- eval/real_pairs.py: extract real pairs (to ~/.local/state/keryx/eval, never the repo), run a
  checkout over a fixed sample, build the blind A/B file, score it. Unit test for the pairing.

## Next
- #70 stays open: about 40% of summaries still mislead (pending-as-done, invented, who-flipped).
  Next levers per the issue: gemma3:12b, a judge pass. Fresh-reader round, CI, merge.
