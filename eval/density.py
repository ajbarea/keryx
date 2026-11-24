"""How many prompt tokens the shipped prompt costs per character of reply, on gemma3:4b.

    uv run python eval/density.py replies.json replies-r1-3.json > eval/tally-density.txt

Files are read from data/: round 4's replies.json, and rounds 1 to 3's kept as replies-r1-3.json.
Each reply is cut to MAX_INPUT_CHARS as model_input cuts it, from the raw text: clean_for_speech,
which drops some text and spells some out ("#123" reads "number 123"), is not applied.
Each is sent with the shipped system prompt and examples; Ollama's
prompt_eval_count is the prompt size. Prints the fixed overhead, then per file the replies' most
tokens per character (the overhead taken off), their largest prompt and their longest reply,
and one synthetic reply dense in IDs at the cap (keryx#105).
"""

import json
import random
import sys
import urllib.request
from pathlib import Path

from keryx.summarize import (
    EXAMPLES,
    MAX_INPUT_CHARS,
    NUM_CTX,
    NUM_PREDICT,
    SYSTEM_PROMPT,
    _framed,
    model_input,
)

MODEL = "gemma3:4b"
HOST = "http://localhost:11434"
DATA = Path(__file__).parent / "data"


def prompt_tokens(message: str) -> int:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for reply, spoken in EXAMPLES:
        messages += [
            {"role": "user", "content": _framed(reply)},
            {"role": "assistant", "content": spoken},
        ]
    messages.append({"role": "user", "content": _framed(message)})
    # A context larger than keryx asks for, so an overflowing prompt is counted whole.
    body = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"num_predict": 1, "num_ctx": 2 * NUM_CTX, "temperature": 0},
    }
    req = urllib.request.Request(
        f"{HOST}/api/chat", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["prompt_eval_count"]


def id_dense(chars: int) -> str:
    rng = random.Random(1)
    parts: list[str] = []
    while sum(map(len, parts)) + len(parts) < chars:
        parts.append(
            rng.choice(
                [
                    f"v{rng.randint(0, 9)}.{rng.randint(0, 99)}.{rng.randint(0, 999)}",
                    f"{rng.randint(0, 99)}.{rng.randint(0, 9)}%",
                    f"#{rng.randint(100, 99999)}",
                    f"{rng.getrandbits(40):x}",
                    f"run 4532{rng.randint(100000, 999999)}",
                ]
            )
        )
    return " ".join(parts)


def main() -> None:
    paths = [DATA / p for p in sys.argv[1:]] or [DATA / "replies.json"]
    overhead = prompt_tokens("")
    room = NUM_CTX - NUM_PREDICT
    print(f"model {MODEL}; overhead {overhead} tokens; room {room} tokens", end="")
    print(f" ({NUM_CTX} context less {NUM_PREDICT})")
    print(f"{'input':<24}{'replies':>8}{'max tok/char':>14}{'max prompt':>12}{'longest':>9}")
    for path in paths:
        raw = [t for t in json.loads(path.read_text()) if isinstance(t, str) and t.strip()]
        sizes = [(prompt_tokens(model_input(t)), len(model_input(t))) for t in raw]
        ratio = max((n - overhead) / c for n, c in sizes)
        longest = max(map(len, raw))
        print(f"{path.name:<24}{len(sizes):>8}{ratio:>14.2f}{max(n for n, _ in sizes):>12}", end="")
        print(f"{longest:>9}")
    dense = model_input(id_dense(2 * MAX_INPUT_CHARS))
    n = prompt_tokens(dense)
    print(f"{'ID-dense, at the cap':<24}{1:>8}{(n - overhead) / len(dense):>14.2f}{n:>12}", end="")
    print(f"{len(dense):>9}")


if __name__ == "__main__":
    main()
