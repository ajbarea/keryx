"""Shuffle model outputs into lettered candidates for a blind judge.

    uv run python eval/blind.py NAME results-TAG.json:MODEL [results-TAG.json:MODEL ...]

Writes data/blind-NAME.json (what the judge reads) and data/key-NAME.json (letters
back to TAG:MODEL; the judge must not read it).
"""

import json
import random
import string
import sys
from pathlib import Path

from keryx.summarize import SPOKEN_MAX_CHARS
from keryx.text import clean_for_speech, first_sentences

DATA = Path(__file__).parent / "data"


def main() -> None:
    name, specs = sys.argv[1], sys.argv[2:]
    replies = json.loads((DATA / "replies.json").read_text())
    sources = {}
    for spec in specs:
        file, model = spec.split(":", 1)
        tag = file.removeprefix("results-").removesuffix(".json")
        sources[f"{tag}:{model}"] = json.loads((DATA / file).read_text())[model]["outs"]
    random.seed(name)
    key, items = {}, []
    for i, reply in enumerate(replies):
        if next(iter(sources.values()))[i] is None:
            continue
        order = list(sources)
        random.shuffle(order)
        candidates = {}
        for letter, src in zip(string.ascii_uppercase, order, strict=False):
            spoken = clean_for_speech(sources[src][i]).strip("\"' ")
            candidates[letter] = first_sentences(spoken, SPOKEN_MAX_CHARS)
            key[f"{i}{letter}"] = src
        items.append({"item": i, "reply": clean_for_speech(reply), "candidates": candidates})
    (DATA / f"blind-{name}.json").write_text(json.dumps(items, indent=1))
    (DATA / f"key-{name}.json").write_text(json.dumps(key))
    print(f"{len(items)} items, {len(sources)} candidates each")


if __name__ == "__main__":
    main()
