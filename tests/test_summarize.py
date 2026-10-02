import json
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
    SPOKEN_MAX_CHARS,
    OllamaClient,
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

    load_seconds: ClassVar[float] = 0.6
    chat_seconds: ClassVar[float] = 0.0
    requests: ClassVar[list[str]] = []

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
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


@pytest.fixture
def slow_ollama():
    SlowOllama.requests = []
    SlowOllama.chat_seconds = 0.0
    server = ThreadingHTTPServer(("127.0.0.1", 0), SlowOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_a_cold_load_longer_than_the_chat_timeout_still_gets_the_gist(slow_ollama):
    client = OllamaClient("m", slow_ollama, timeout=0.2)
    assert SlowOllama.load_seconds > client.timeout
    assert spoken_line(LONG, client) == "I fixed the parser."
    assert SlowOllama.requests == ["/api/generate", "/api/chat"]


def test_generation_is_still_bounded_by_the_short_timeout(slow_ollama):
    SlowOllama.chat_seconds = 0.5
    client = OllamaClient("m", slow_ollama, timeout=0.2, load_timeout=2.0)
    assert spoken_line(LONG, client).startswith("I changed the parser.")


def test_load_timeout_outlasts_the_slowest_cold_load_measured():
    assert LOAD_TIMEOUT > 44


def test_design_doc_states_the_timeouts_in_use():
    design = " ".join(
        (Path(__file__).resolve().parents[1] / "docs" / "design.md").read_text().split()
    )
    assert f"under a {LOAD_TIMEOUT:g} s timeout" in design
    assert f"generates under {GENERATE_TIMEOUT:g} s" in design
