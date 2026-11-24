import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "real_pairs", Path(__file__).parent.parent / "eval" / "real_pairs.py"
)
assert spec is not None and spec.loader is not None
real_pairs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real_pairs)

SID = "11111111-2222-4333-8444-555555555555"


def log(ts, message):
    return json.dumps({"ts": ts, "level": "INFO", "logger": "keryx", "message": message})


def test_a_said_line_pairs_with_the_reply_written_before_it(tmp_path):
    reply = "I merged the fix and the deploy is still running. Want me to watch it?"
    later = "A reply written after the say line, which keryx never saw."
    transcript = tmp_path / f"{SID}.jsonl"
    rows = [
        {
            "type": "assistant",
            "timestamp": "2026-11-23T10:00:00.000Z",
            "message": {"content": [{"type": "text", "text": reply}]},
        },
        {
            "type": "assistant",
            "isSidechain": True,
            "timestamp": "2026-11-23T10:00:01.000Z",
            "message": {"content": [{"type": "text", "text": "a subagent's line"}]},
        },
        {
            "type": "assistant",
            "timestamp": "2026-11-23T10:05:00.000Z",
            "message": {"content": [{"type": "text", "text": later}]},
        },
    ]
    # Compact, as Claude Code writes its transcripts.
    transcript.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows))
    lines = [
        log(
            "2026-11-23T10:00:02.000Z",
            f"say repo {len(reply)} chars session={SID} -> {{'ok': True}}",
        ),
        "not json",
        log(
            "2026-11-23T10:00:03.000Z",
            f"shortened {len(reply)} chars to 'I merged the fix; the deploy runs.' (model) in 0.9s",
        ),
        log(
            "2026-11-23T10:06:00.000Z",
            "say repo 12 chars session=99999999-2222-4333-8444-555555555555 -> {}",
        ),
        log("2026-11-23T10:06:01.000Z", "shortened 12 chars to 'gone' (model) in 0.5s"),
    ]
    pairs = real_pairs.pairs_from(lines, {SID: str(transcript)})
    assert [(p["source"], p["said"], p["path"]) for p in pairs] == [
        (reply, "I merged the fix; the deploy runs.", "model")
    ]
