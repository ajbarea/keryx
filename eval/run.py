"""Run each model over data/replies.json with the shipped prompt.

    uv run python eval/run.py TAG MODEL [MODEL ...]

Writes data/results-TAG.json: per model, load time, VRAM as Ollama reports it,
latency median/max, and every output. Ollama's size_vram undercounts some models
(gemma4:e2b reads 0.22 GB); measure with nvidia-smi before and after a load.
"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from keryx.summarize import DIRECT_MAX_CHARS, SYSTEM_PROMPT, OllamaClient, _framed
from keryx.text import clean_for_speech

DATA = Path(__file__).parent / "data"


def main() -> None:
    tag, models = sys.argv[1], sys.argv[2:]
    replies = json.loads((DATA / "replies.json").read_text())
    out_path = DATA / f"results-{tag}.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    for model in models:
        unload_all = "for m in $(ollama ps | awk 'NR>1{print $1}'); do ollama stop $m; done"
        subprocess.run(unload_all, shell=True)
        client = OllamaClient(model, timeout=300)
        started = time.time()
        client.generate(_framed("warm up"), SYSTEM_PROMPT)
        load = time.time() - started
        ps = json.load(urllib.request.urlopen("http://localhost:11434/api/ps"))["models"][0]
        outs, latencies = [], []
        for reply in replies:
            cleaned = clean_for_speech(reply)
            if len(cleaned) <= DIRECT_MAX_CHARS:
                outs.append(None)  # spoken as-is, never reaches the model
                continue
            started = time.time()
            outs.append(client.generate(_framed(cleaned), SYSTEM_PROMPT).strip())
            latencies.append(time.time() - started)
        latencies.sort()
        results[model] = {
            "load_s": round(load, 1),
            "ollama_vram_gb": round(ps["size_vram"] / 1e9, 2),
            "median_s": round(latencies[len(latencies) // 2], 2),
            "max_s": round(latencies[-1], 2),
            "outs": outs,
        }
        print(model, {k: v for k, v in results[model].items() if k != "outs"}, flush=True)
        out_path.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
