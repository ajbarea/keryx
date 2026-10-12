import http.client
import json
import urllib.error

from keryx import doctor
from keryx.config import Config

TAGS = json.dumps({"models": [{"name": "gemma3:4b"}]}).encode()


def fetch_ok(url: str) -> bytes:
    return TAGS if url.endswith("/api/tags") else b'{"version": "0.12.0"}'


def fetch_down(url: str) -> bytes:
    raise urllib.error.URLError("connection refused")


def which_all(name: str) -> str:
    return f"/usr/bin/{name}"


def lines(found):
    return {c.name: c.status for c in found}


def test_all_present():
    found = doctor.checks(Config(), which=which_all, fetch=fetch_ok)
    assert lines(found) == {
        "uv": "ok",
        "powershell.exe": "ok",
        "ollama": "ok",
        "model": "ok",
        "audio-dir": "ok",
    }
    assert doctor.render(found).splitlines()[-1] == "result: ready"
    assert doctor.exit_code(found) == 0


def test_missing_uv_and_powershell():
    found = doctor.checks(Config(), which=lambda _n: None, fetch=fetch_ok)
    text = doctor.render(found)
    assert "missing uv: not on PATH" in text
    assert "  fix: curl -LsSf https://astral.sh/uv/install.sh | sh" in text.splitlines()
    assert lines(found)["powershell.exe"] == "missing"
    assert doctor.exit_code(found) == 1


def test_ollama_down_names_serve_or_install():
    found = doctor.checks(Config(), which=which_all, fetch=fetch_down)
    assert lines(found)["ollama"] == "missing" and lines(found)["model"] == "n/a"
    assert "  fix: ollama serve" in doctor.render(found).splitlines()
    no_ollama = doctor.checks(
        Config(), which=lambda n: None if n == "ollama" else which_all(n), fetch=fetch_down
    )
    assert "  fix: curl -fsSL https://ollama.com/install.sh | sh" in doctor.render(no_ollama)


def test_model_not_pulled():
    found = doctor.checks(Config(model="qwen3:8b"), which=which_all, fetch=fetch_ok)
    assert lines(found)["model"] == "missing"
    assert "  fix: ollama pull qwen3:8b" in doctor.render(found).splitlines()


def test_untagged_model_matches_latest():
    tags = json.dumps({"models": [{"name": "gemma3:latest"}]}).encode()
    found = doctor.checks(
        Config(model="gemma3"),
        which=which_all,
        fetch=lambda u: tags if u.endswith("/api/tags") else b"{}",
    )
    assert lines(found)["model"] == "ok"


def test_no_model_skips_ollama():
    found = doctor.checks(Config(model=""), which=which_all, fetch=fetch_down)
    assert lines(found)["ollama"] == "n/a" and lines(found)["model"] == "n/a"


def test_audio_dir_off_a_windows_drive():
    found = doctor.checks(Config(audio_dir="/tmp/keryx"), which=which_all, fetch=fetch_ok)
    assert lines(found)["audio-dir"] == "missing"


def test_non_object_tags_payload_is_not_a_traceback():
    found = doctor.checks(
        Config(), which=which_all, fetch=lambda u: b"[]" if u.endswith("/api/tags") else b"{}"
    )
    assert lines(found)["ollama"] == "missing"
    assert doctor.exit_code(found) == 1


def test_http_errors_are_a_missing_ollama_not_a_traceback():
    def bad_status(url: str) -> bytes:
        raise http.client.BadStatusLine("SSH-2.0")

    def bad_port(url: str) -> bytes:
        raise http.client.InvalidURL("nonnumeric port: 'abc'")

    for fetch in (bad_status, bad_port):
        found = doctor.checks(Config(), which=which_all, fetch=fetch)
        assert lines(found)["ollama"] == "missing"
        assert "  fix: ollama serve" in doctor.render(found).splitlines()
