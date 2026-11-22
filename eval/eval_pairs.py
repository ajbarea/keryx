"""Evaluate faithfulness across real failure pairs from keryx#70.

Usage:
    uv run python eval/eval_pairs.py [MODEL]

Without arguments, tests the rule checker against the committed failure and faithful pairs.
With MODEL, runs each source message through the model via Ollama and evaluates the summary.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from keryx.summarize import OllamaClient, check_faithfulness, is_faithful, spoken

PAIRS_FILE = Path(__file__).parent / "pairs.json"


def evaluate_static() -> int:
    pairs = json.loads(PAIRS_FILE.read_text())
    print(f"Evaluating {len(pairs)} pairs against faithfulness rules...\n")
    failed = 0
    for i, pair in enumerate(pairs, 1):
        cat = pair["category"]
        source = pair["source"]
        bad_sum = pair.get("bad_summary")
        good_sum = pair.get("good_summary")

        if bad_sum:
            valid, reason = check_faithfulness(bad_sum, source)
            if valid:
                print(f"[{i}] FAIL: Bad summary in '{cat}' was not flagged as unfaithful!")
                print(f"    Source:  {source[:60]}...")
                print(f"    Summary: {bad_sum}")
                failed += 1
            else:
                print(f"[{i}] OK: Flagged '{cat}' (reason: {reason})")

        if good_sum:
            valid, reason = check_faithfulness(good_sum, source)
            if not valid:
                print(
                    f"[{i}] FAIL: Good summary in '{cat}' was incorrectly flagged "
                    f"as unfaithful ({reason})!"
                )
                print(f"    Summary: {good_sum}")
                failed += 1
            else:
                print(f"[{i}] OK: Good summary passed faithfulness check.")

    print(f"\nStatic eval complete: {len(pairs) - failed}/{len(pairs)} passed.")
    return 1 if failed else 0


def evaluate_model(model: str) -> int:
    pairs = json.loads(PAIRS_FILE.read_text())
    print(f"Evaluating model '{model}' over {len(pairs)} test cases...\n")
    client = OllamaClient(model, timeout=120)
    failed = 0

    print(f"{'#':<3} {'Category':<28} {'Faithful':<10} {'Path':<10} {'Latency':<8} Summary")
    print("-" * 90)

    for i, pair in enumerate(pairs, 1):
        cat = pair["category"]
        source = pair["source"]
        t0 = time.monotonic()
        line, path = spoken(source, client)
        dt = time.monotonic() - t0
        faithful = is_faithful(line, source)
        if not faithful:
            failed += 1
        status = "OK" if faithful else "FAIL"
        print(f"{i:<3} {cat:<28} {status:<10} {path:<10} {dt:.2f}s    {line[:50]}")

    print("-" * 90)
    print(f"Model eval complete: {len(pairs) - failed}/{len(pairs)} faithful.")
    return 1 if failed else 0


def main() -> int:
    if len(sys.argv) > 1:
        return evaluate_model(sys.argv[1])
    return evaluate_static()


if __name__ == "__main__":
    sys.exit(main())
