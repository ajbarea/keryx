"""Un-blind data/scores-NAME.json and print per-candidate totals.

uv run python eval/tally.py NAME
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).parent / "data"


def main() -> None:
    name = sys.argv[1]
    scores = json.loads((DATA / f"scores-{name}.json").read_text())
    key = json.loads((DATA / f"key-{name}.json").read_text())
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    for item, by_letter in scores.items():
        for letter, (faithful, useful, speakable) in by_letter.items():
            t = totals[key[f"{item}{letter}"]]
            t[0] += faithful
            t[1] += useful
            t[2] += speakable
            t[3] += faithful == 0
            t[4] += 1
    print(f"{'candidate':40} faithful useful speakable total unfaithful items")
    for src, t in sorted(totals.items(), key=lambda kv: -sum(kv[1][:3])):
        print(f"{src:40} {t[0]:8} {t[1]:6} {t[2]:9} {sum(t[:3]):5} {t[3]:10} {t[4]:5}")


if __name__ == "__main__":
    main()
