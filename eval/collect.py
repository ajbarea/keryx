"""Collect end-of-turn replies from local Claude Code transcripts into data/replies.json.

The replies are private session text, so data/ is gitignored.
"""

import glob
import json
import os
import random
from pathlib import Path

N = 20
OUT = Path(__file__).parent / "data" / "replies.json"


def end_of_turn_replies(path: str) -> list[str]:
    replies, last = [], None
    with open(path) as fh:
        lines = list(fh)
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "assistant":
            content = d.get("message", {}).get("content", [])
            text = "".join(
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            )
            if text.strip():
                last = text
        elif d.get("type") == "user" and last:
            content = d.get("message", {}).get("content")
            typed = isinstance(content, str) or (
                isinstance(content, list)
                and any(isinstance(c, dict) and c.get("type") == "text" for c in content)
            )
            if typed:
                replies.append(last)
                last = None
    return replies


def main() -> None:
    pattern = os.path.expanduser("~/.claude/projects/*/*.jsonl")
    files = sorted(glob.glob(pattern), key=os.path.getmtime)
    replies = [r for f in files[-60:] for r in end_of_turn_replies(f) if 150 < len(r) < 6000]
    random.seed(7)
    random.shuffle(replies)
    replies.sort(key=len)
    picked = [replies[int(i * (len(replies) - 1) / (N - 1))] for i in range(N)]
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(picked, indent=1))
    print(f"{len(replies)} candidates, kept {N} spread by length")


if __name__ == "__main__":
    main()
