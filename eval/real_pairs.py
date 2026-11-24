"""Measure spoken summaries on your own real replies (keryx#70).

Real pairs are private (your assistant's replies), so everything this writes goes to
--dir (default ~/.local/state/keryx/eval), never into the repo.

    uv run python eval/real_pairs.py extract        # daemon.log + Claude Code transcripts
    uv run python eval/real_pairs.py run main       # this checkout's spoken() over a sample
    uv run python eval/real_pairs.py run pr         # ...again on another checkout or model
    uv run python eval/real_pairs.py blind main pr  # an A/B file with the labels hidden
    # a reader (a person or a strong model) fills judge-out.json from judge-in.json
    uv run python eval/real_pairs.py score          # unblind: unfaithful, point lost, preferred

Each `say ... N chars session=S` line in daemon.log followed by `shortened N chars to '...'`
is matched to the last assistant text in transcript S written before it.
"""

from __future__ import annotations

import argparse
import ast
import collections
import glob
import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from keryx.config import Config, log_dir
from keryx.summarize import OllamaClient, spoken

SAY = re.compile(r"^say \S+ (\d+) chars session=([0-9a-f-]{36})")
SHORT = re.compile(r"^shortened (\d+) chars to (.*) \((model|fallback|trimmed[^)]*)\) in")
JUDGE_RUBRIC = (
    "For each item, judge A and B against the source only. verdict: faithful or unfaithful "
    "(a listener would believe something false); category when unfaithful: offer_as_done, "
    "removed_as_done, draft_as_own_act, who_flipped, pending_as_done, invented, other_false; "
    "main_point: kept or lost; then better: A, B or tie. Write a list of "
    '{"id", "A": {"verdict", "category", "main_point"}, "B": {...}, "better"}.'
)


def _when(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def _texts(path: str) -> list[tuple[float, str]]:
    out = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if '"type":"assistant"' not in line or '"text"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isSidechain") or not d.get("timestamp"):
                continue
            parts = d.get("message", {}).get("content", [])
            text = "".join(
                c.get("text", "") for c in parts if isinstance(c, dict) and c.get("type") == "text"
            ).strip()
            if text:
                out.append((_when(d["timestamp"]), text))
    return out


def pairs_from(log_lines, transcripts: dict[str, str]) -> list[dict]:
    """(reply, spoken) pairs from daemon.log lines; `transcripts` maps session id to its file."""
    pending: dict[str, tuple[str, float]] = {}
    cache: dict[str, list[tuple[float, str]]] = {}
    pairs = []
    for line in log_lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        message = d.get("message", "")
        if m := SAY.match(message):
            pending[m.group(1)] = (m.group(2), _when(d["ts"]))
            continue
        m = SHORT.match(message)
        if not m or m.group(1) not in pending:
            continue
        sid, at = pending.pop(m.group(1))
        try:
            said = ast.literal_eval(m.group(2))
        except (ValueError, SyntaxError):
            continue
        if sid not in transcripts:
            continue
        cache.setdefault(sid, _texts(transcripts[sid]))
        before = [t for when, t in cache[sid] if when <= at + 2]
        n = int(m.group(1))
        # The transcript's text, not a later one, has about the length keryx logged.
        if before and abs(len(before[-1]) - n) <= max(40, n * 0.1):
            pairs.append({"at": d["ts"], "source": before[-1], "said": said, "path": m.group(3)})
    return pairs


def extract(out: Path) -> None:
    logs = [log_dir() / "daemon.log.1", log_dir() / "daemon.log"]
    lines = [
        line for f in logs if f.exists() for line in f.read_text(errors="replace").splitlines()
    ]
    transcripts = {
        Path(f).stem: f for f in glob.glob(str(Path.home() / ".claude*/projects/*/*.jsonl"))
    }
    pairs = pairs_from(lines, transcripts)
    (out / "pairs.json").write_text(json.dumps(pairs))
    print(f"{len(pairs)} pairs in {out / 'pairs.json'}")


def sample(out: Path, n: int, seed: int) -> list[dict]:
    pairs = [p for p in json.loads((out / "pairs.json").read_text()) if p["path"] == "model"]
    random.Random(seed).shuffle(pairs)
    return pairs[:n]


def run(out: Path, tag: str, n: int, seed: int) -> None:
    cfg = Config.load()
    client = OllamaClient(cfg.model, cfg.ollama_host)
    rows = []
    for p in sample(out, n, seed):
        start = time.monotonic()
        line, path = spoken(p["source"], client)
        rows.append({"line": line, "path": path, "s": round(time.monotonic() - start, 2)})
    (out / f"run-{tag}.json").write_text(json.dumps({"model": cfg.model, "rows": rows}))
    paths = collections.Counter(r["path"] for r in rows)
    print(
        f"{tag}: {cfg.model}, {dict(paths)}, median {sorted(r['s'] for r in rows)[len(rows) // 2]}s"
    )


def blind(out: Path, a_tag: str, b_tag: str, n: int, seed: int) -> None:
    runs = {t: json.loads((out / f"run-{t}.json").read_text())["rows"] for t in (a_tag, b_tag)}
    rng, items, key = random.Random(seed + 1), [], {}
    for i, p in enumerate(sample(out, n, seed)):
        sides = [(runs[a_tag][i]["line"], a_tag), (runs[b_tag][i]["line"], b_tag)]
        rng.shuffle(sides)
        key[i] = {"A": sides[0][1], "B": sides[1][1]}
        items.append({"id": i, "source": p["source"], "A": sides[0][0], "B": sides[1][0]})
    (out / "judge-in.json").write_text(json.dumps({"rubric": JUDGE_RUBRIC, "items": items}))
    (out / "judge-key.json").write_text(json.dumps(key))
    print(f"{len(items)} items in {out / 'judge-in.json'}; write the verdicts to judge-out.json")


def score(out: Path) -> None:
    verdicts = json.loads((out / "judge-out.json").read_text())
    key = json.loads((out / "judge-key.json").read_text())
    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for v in verdicts:
        sides = key[str(v["id"])]
        for side in ("A", "B"):
            tally[sides[side]]["unfaithful"] += v[side]["verdict"] == "unfaithful"
            tally[sides[side]]["main point lost"] += v[side]["main_point"] == "lost"
        tally[sides.get(v["better"], "tie")]["preferred"] += 1
    for tag, counts in sorted(tally.items()):
        print(f"{tag}: {dict(counts)} of {len(verdicts)}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("step", choices=("extract", "run", "blind", "score"))
    ap.add_argument("tags", nargs="*")
    ap.add_argument("--dir", type=Path, default=Path.home() / ".local/state/keryx/eval")
    ap.add_argument("-n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=70)
    a = ap.parse_args(argv)
    a.dir.mkdir(parents=True, exist_ok=True)
    if a.step == "extract":
        extract(a.dir)
    elif a.step == "run":
        run(a.dir, (a.tags or ["run"])[0], a.n, a.seed)
    elif a.step == "blind":
        if len(a.tags) != 2:
            ap.error("blind takes two run tags")
        blind(a.dir, a.tags[0], a.tags[1], a.n, a.seed)
    else:
        score(a.dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
