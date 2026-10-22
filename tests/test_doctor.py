import http.client
import json
import subprocess
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


def env_unset():
    return {}


def env_tuned():
    return {"OLLAMA_KV_CACHE_TYPE": "q8_0", "OLLAMA_FLASH_ATTENTION": "1"}


def env_none():
    return None


def ps_fetch(ps: bytes):
    return lambda url: ps if url.endswith("/api/ps") else fetch_ok(url)


def by_name(found):
    return {c.name: c for c in found}


def lines(found):
    return {c.name: c.status for c in found}


def test_all_present():
    found = doctor.checks(Config(), which=which_all, fetch=fetch_ok, server_env=env_tuned)
    assert lines(found) == {
        "uv": "ok",
        "powershell.exe": "ok",
        "ollama": "ok",
        "model": "ok",
        "ollama-memory": "ok",
        "ollama-loaded": "ok",
        "audio-dir": "ok",
    }
    assert doctor.render(found).splitlines()[-1] == "result: ready"
    assert doctor.exit_code(found) == 0


def test_missing_uv_and_powershell():
    found = doctor.checks(Config(), which=lambda _n: None, fetch=fetch_ok, server_env=env_none)
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
    found = doctor.checks(
        Config(model="qwen3:8b"), which=which_all, fetch=fetch_ok, server_env=env_none
    )
    assert lines(found)["model"] == "missing"
    assert "  fix: ollama pull qwen3:8b" in doctor.render(found).splitlines()


def test_untagged_model_matches_latest():
    tags = json.dumps({"models": [{"name": "gemma3:latest"}]}).encode()
    found = doctor.checks(
        Config(model="gemma3"),
        which=which_all,
        fetch=lambda u: tags if u.endswith("/api/tags") else b"{}",
        server_env=env_none,
    )
    assert lines(found)["model"] == "ok"


def test_no_model_skips_ollama():
    found = doctor.checks(Config(model=""), which=which_all, fetch=fetch_down)
    assert lines(found)["ollama"] == "n/a" and lines(found)["model"] == "n/a"


def test_audio_dir_off_a_windows_drive():
    found = doctor.checks(
        Config(audio_dir="/tmp/keryx"), which=which_all, fetch=fetch_ok, server_env=env_none
    )
    assert lines(found)["audio-dir"] == "missing"


def test_non_object_tags_payload_is_not_a_traceback():
    found = doctor.checks(
        Config(),
        which=which_all,
        fetch=lambda u: b"[]" if u.endswith("/api/tags") else b"{}",
        server_env=env_none,
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


def run_memory(env, ps=b'{"models": []}', model="gemma3:4b"):
    found = doctor.checks(Config(model=model), which=which_all, fetch=ps_fetch(ps), server_env=env)
    return found, by_name(found)


def test_unset_server_env_is_optional_with_the_drop_in_fix():
    found, got = run_memory(env_unset)
    assert got["ollama-memory"].status == "optional"
    assert got["ollama-memory"].detail == (
        "kv_cache=f16 (unset), flash_attention=auto (unset), keep_alive=5m (unset)"
    )
    text = doctor.render(found).splitlines()
    assert (
        "optional ollama-memory: kv_cache=f16 (unset), flash_attention=auto (unset),"
        " keep_alive=5m (unset)" in text
    )
    assert (
        "  fix: sudo systemctl edit ollama  # add OLLAMA_KV_CACHE_TYPE=q8_0 and"
        " OLLAMA_FLASH_ATTENTION=1; see docs/troubleshooting.md#ollama-server-memory"
    ) in text
    assert text[-1] == "result: ready"
    assert doctor.exit_code(found) == 0


def test_kv_cache_without_flash_attention_is_still_optional():
    _, got = run_memory(lambda: {"OLLAMA_KV_CACHE_TYPE": "q8_0"})
    assert got["ollama-memory"].status == "optional"


def test_tuned_server_env_is_ok_and_shows_values():
    env = {**env_tuned(), "OLLAMA_KEEP_ALIVE": "30m"}
    found, got = run_memory(lambda: env)
    assert got["ollama-memory"].status == "ok"
    assert got["ollama-memory"].detail == "kv_cache=q8_0, flash_attention=1, keep_alive=30m"
    assert got["ollama-memory"].fixes == ()
    assert "ok ollama-memory: kv_cache=q8_0, flash_attention=1, keep_alive=30m" in doctor.render(
        found
    )


def test_q4_0_counts_as_tuned():
    _, got = run_memory(lambda: {"OLLAMA_KV_CACHE_TYPE": "q4_0", "OLLAMA_FLASH_ATTENTION": "1"})
    assert got["ollama-memory"].status == "ok"


def test_not_a_systemd_service_is_na():
    _, got = run_memory(env_none)
    assert got["ollama-memory"].status == "n/a"
    assert got["ollama-memory"].detail == (
        "not a systemd service; see the docs for its memory settings"
    )


def test_loaded_models_show_context_and_gpu_gb():
    ps = json.dumps(
        {
            "models": [
                {"name": "gemma3:4b", "context_length": 4096, "size_vram": 3 * 1024**3},
                {"name": "qwen3:8b", "context_length": 8192, "size_vram": int(5.5 * 1024**3)},
            ]
        }
    ).encode()
    found, got = run_memory(env_tuned, ps)
    assert got["ollama-loaded"].status == "ok"
    assert got["ollama-loaded"].detail == (
        "gemma3:4b (context 4096, 3.0 GB GPU), qwen3:8b (context 8192, 5.5 GB GPU)"
    )
    assert "ok ollama-loaded: gemma3:4b (context 4096, 3.0 GB GPU), qwen3:8b" in doctor.render(
        found
    )


def test_no_loaded_models_reads_none():
    _, got = run_memory(env_tuned, b'{"models": []}')
    assert got["ollama-loaded"] == doctor.Check("ok", "ollama-loaded", "none")


def test_ps_failure_is_na():
    def fetch(url: str) -> bytes:
        if url.endswith("/api/ps"):
            raise urllib.error.URLError("boom")
        return fetch_ok(url)

    found = doctor.checks(Config(), which=which_all, fetch=fetch, server_env=env_tuned)
    assert by_name(found)["ollama-loaded"].status == "n/a"
    for bad in (b"not json", b"[]", b'{"models": [1]}'):
        _, got = run_memory(env_tuned, bad)
        assert got["ollama-loaded"].status == "n/a"


def test_memory_checks_skipped_without_a_model_or_ollama():
    for cfg, fetch in ((Config(model=""), fetch_ok), (Config(), fetch_down)):
        found = doctor.checks(cfg, which=which_all, fetch=fetch, server_env=env_unset)
        assert "ollama-memory" not in lines(found)
        assert "ollama-loaded" not in lines(found)


def fake_run(outputs, calls=None):
    """Answer `systemctl show ollama -p <prop> --value` from a dict of prop -> stdout."""

    def run(cmd, **kwargs):
        if calls is not None:
            calls.append((cmd, kwargs))
        out = outputs[cmd[cmd.index("-p") + 1]]
        if isinstance(out, BaseException):
            raise out
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")

    return run


def test_systemd_env_parses_quoted_values_and_ignores_other_vars():
    calls = []
    run = fake_run(
        {
            "LoadState": "loaded\n",
            "Environment": (
                'PATH=/usr/local/bin:/my dir/bin "OLLAMA_KV_CACHE_TYPE=q8_0" '
                "OLLAMA_FLASH_ATTENTION=1 'OLLAMA_KEEP_ALIVE=10m' OLLAMAX=no\n"
            ),
        },
        calls,
    )
    assert doctor._systemd_env(run) == {
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_KEEP_ALIVE": "10m",
    }
    assert all(kw["timeout"] == 2 for _, kw in calls)
    assert calls[0][0][:3] == ["systemctl", "show", "ollama"]


def test_systemd_env_unit_with_no_environment_is_empty_dict():
    run = fake_run({"LoadState": "loaded\n", "Environment": "\n"})
    assert doctor._systemd_env(run) == {}


def test_systemd_env_missing_unit_is_none():
    run = fake_run({"LoadState": "not-found\n", "Environment": "\n"})
    assert doctor._systemd_env(run) is None


def test_systemd_env_failures_are_none():
    for exc in (
        FileNotFoundError("systemctl"),
        subprocess.TimeoutExpired("systemctl", 2),
        PermissionError("denied"),
    ):
        assert doctor._systemd_env(fake_run({"LoadState": exc, "Environment": exc})) is None

    def failing(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="no bus")

    assert doctor._systemd_env(failing) is None


def test_systemd_env_unparseable_quoting_is_none():
    run = fake_run({"LoadState": "loaded\n", "Environment": 'OLLAMA_X="unterminated\n'})
    assert doctor._systemd_env(run) is None
