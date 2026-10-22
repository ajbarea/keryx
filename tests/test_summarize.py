import json
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from keryx.summarize import (
    DIRECT_MAX_CHARS,
    GENERATE_TIMEOUT,
    LOAD_TIMEOUT,
    MAX_INPUT_CHARS,
    NUM_CTX,
    NUM_PREDICT,
    SPOKEN_MAX_CHARS,
    OllamaClient,
    model_input,
    ollama_keep_alive,
    spoken_line,
)


class FakeClient:
    def __init__(self, reply="I fixed it. Please review the PR.", exc=None):
        self.reply = reply
        self.exc = exc
        self.prompts: list[str] = []

    def generate(self, prompt, system):
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return self.reply


LONG = "I changed the parser. " * 20


def test_short_reply_is_spoken_directly_without_the_model():
    client = FakeClient()
    assert spoken_line("**Done.** Tests pass.", client) == "Done. Tests pass."
    assert client.prompts == []


def test_long_reply_goes_through_the_model_with_cleaned_text():
    client = FakeClient()
    assert spoken_line(LONG + "\n```\ncode()\n```", client) == "I fixed it. Please review the PR."
    assert "code()" not in client.prompts[0]
    assert len(LONG) > DIRECT_MAX_CHARS


def test_model_output_is_cleaned_and_unquoted():
    client = FakeClient(reply='"**I fixed** `src/a/b.py`."')
    assert spoken_line(LONG, client) == "I fixed b.py."


def test_model_down_falls_back_to_opening_sentences():
    client = FakeClient(exc=urllib.error.URLError("refused"))
    out = spoken_line(LONG, client)
    assert out.startswith("I changed the parser.")
    assert len(out) <= SPOKEN_MAX_CHARS


def test_empty_model_output_falls_back():
    assert spoken_line(LONG, FakeClient(reply="   ")).startswith("I changed the parser.")


def test_no_client_falls_back():
    assert spoken_line(LONG, None).startswith("I changed the parser.")


def test_code_only_reply_is_silent():
    assert spoken_line("```\nx = 1\n```", FakeClient()) == ""


class SlowOllama(BaseHTTPRequestHandler):
    """Loads slower than the chat timeout, then chats instantly."""

    load_seconds: ClassVar[float] = 2.0
    chat_seconds: ClassVar[float] = 0.0
    requests: ClassVar[list[str]] = []
    bodies: ClassVar[list[dict]] = []

    def do_POST(self):
        self.bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.requests.append(self.path)
        if self.path == "/api/generate":
            time.sleep(self.load_seconds)
            body = {"done": True}
        else:
            time.sleep(self.chat_seconds)
            body = {"message": {"content": "I fixed the parser."}}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        # A client that timed out leaves the handler a broken pipe; anything else is a bug.
        if not isinstance(sys.exc_info()[1], BrokenPipeError | ConnectionResetError):
            super().handle_error(request, client_address)


@pytest.fixture
def slow_ollama():
    SlowOllama.requests = []
    SlowOllama.bodies = []
    SlowOllama.chat_seconds = 0.0
    SlowOllama.load_seconds = 2.0
    server = QuietServer(("127.0.0.1", 0), SlowOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_a_cold_load_longer_than_the_chat_timeout_still_gets_the_gist(slow_ollama):
    client = OllamaClient("m", slow_ollama, timeout=1.0)
    assert SlowOllama.load_seconds > client.timeout
    assert spoken_line(LONG, client) == "I fixed the parser."
    assert SlowOllama.requests == ["/api/generate", "/api/chat"]


def test_generation_is_still_bounded_by_the_short_timeout(slow_ollama):
    SlowOllama.load_seconds = 0.0
    SlowOllama.chat_seconds = 3.0
    client = OllamaClient("m", slow_ollama, timeout=1.0, load_timeout=5.0)
    assert spoken_line(LONG, client).startswith("I changed the parser.")


def test_load_timeout_outlasts_the_slowest_cold_load_measured():
    assert LOAD_TIMEOUT > 44


def test_design_doc_states_the_timeouts_in_use():
    design = " ".join(
        (Path(__file__).resolve().parents[1] / "docs" / "design.md").read_text().split()
    )
    assert f"under a {LOAD_TIMEOUT:g} s timeout" in design
    assert f"generates under {GENERATE_TIMEOUT:g} s" in design
    assert f"a {NUM_CTX}-token context" in design
    assert f"up to {MAX_INPUT_CHARS} characters" in design


# Measured on gemma3:4b, Ollama 0.35.0, 2026-10-21: fixed prompt overhead in tokens and
# dense text (versions, IDs, percentages) in tokens per char.
OVERHEAD_TOKENS = 409
DENSE_TOKENS_PER_CHAR = 0.63


def test_the_largest_prompt_keryx_can_send_fits_the_context_it_asks_for():
    worst = OVERHEAD_TOKENS + DENSE_TOKENS_PER_CHAR * MAX_INPUT_CHARS + NUM_PREDICT
    assert worst <= NUM_CTX


def test_chat_and_warm_pin_the_context_window(slow_ollama):
    SlowOllama.load_seconds = 0.0
    client = OllamaClient("m", host=slow_ollama)
    assert client.generate("hi", "sys") == "I fixed the parser."
    by_path = dict(zip(SlowOllama.requests, SlowOllama.bodies, strict=True))
    assert by_path["/api/generate"]["options"]["num_ctx"] == NUM_CTX
    assert by_path["/api/chat"]["options"]["num_ctx"] == NUM_CTX
    assert by_path["/api/chat"]["options"]["num_predict"] == NUM_PREDICT


def test_a_huge_reply_is_capped_before_it_reaches_the_model(slow_ollama):
    SlowOllama.load_seconds = 0.0
    huge = "I changed the parser in a few places. " * 1000
    assert len(huge) > 5 * MAX_INPUT_CHARS
    spoken_line(huge, OllamaClient("m", host=slow_ollama))
    chat = next(
        b for p, b in zip(SlowOllama.requests, SlowOllama.bodies, strict=True) if p == "/api/chat"
    )
    sent = chat["messages"][-1]["content"]
    message = sent.removeprefix("Message to rewrite:\n<message>\n").removesuffix("\n</message>")
    assert 0 < len(message) <= MAX_INPUT_CHARS


@pytest.mark.parametrize(
    "reply",
    [
        "Done. " + "b" * 5594 + ".",
        "Note: " + "x" * 6100,
        "I changed the parser. " * 400 + "Should the old name stay?",
    ],
)
def test_a_reply_over_the_cap_keeps_its_opening_and_its_close(reply):
    sent = model_input(reply)
    assert len(sent) <= MAX_INPUT_CHARS
    assert sent.startswith(reply[:4])
    assert sent.endswith(reply[-4:])


def test_a_reply_within_the_cap_reaches_the_model_whole():
    reply = "word " * (MAX_INPUT_CHARS // 5)
    assert model_input(reply) == reply


@pytest.mark.parametrize(
    ("value", "sent"),
    [
        ("5m", 300),
        ("0", 0),
        ("300", 300),
        ("90.5", 90.5),
        ("1h30m", 5400),
        ("1.5h", 5400),
        ("-1", -1),
        ("-1m", -1),
        (" 10m ", 600),
        ("9999999h", -1),
        ("1e10", -1),
    ],
)
def test_ollama_gets_keep_alive_as_seconds(value, sent):
    # A number always: Go's ParseDuration rejects strings this side cannot vouch for, and
    # Ollama overflows past about 9.2e9 s to a negative duration that unloads at once.
    assert ollama_keep_alive(value) == sent


@pytest.mark.parametrize(("setting", "sent"), [("0", 0), ("10m", 600)])
def test_keep_alive_reaches_both_requests(slow_ollama, setting, sent):
    SlowOllama.load_seconds = 0.0
    client = OllamaClient("m", slow_ollama, keep_alive=setting)
    assert client.generate("p", "s") == "I fixed the parser."
    assert SlowOllama.requests == ["/api/generate", "/api/chat"]
    assert [b["keep_alive"] for b in SlowOllama.bodies] == [sent, sent]
    assert SlowOllama.bodies[1]["keep_alive"] == sent
