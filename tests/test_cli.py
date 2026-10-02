import io
import json

import pytest

from keryx import __main__ as cli
from keryx import client
from keryx.config import Config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    for key in ("KERYX_ENABLED", "KERYX_VOICE", "KERYX_MODEL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def sent(monkeypatch):
    calls = {"send": [], "spawn": []}

    def fake_send(req, *a, **k):
        calls["send"].append(req)
        raise FileNotFoundError

    monkeypatch.setattr(client, "send", fake_send)
    monkeypatch.setattr(client, "send_or_spawn", lambda req, *a, **k: calls["spawn"].append(req))
    return calls


def run_hook(monkeypatch, event):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    return cli.main(["hook"])


def test_stop_event_spawns_daemon_if_needed(monkeypatch, sent):
    event = {"hook_event_name": "Stop", "session_id": "s", "last_assistant_message": "Done."}
    assert run_hook(monkeypatch, event) == 0
    assert sent["spawn"][0]["op"] == "say"


def test_prompt_submit_spawns_so_the_voice_loads_early(monkeypatch, sent):
    assert run_hook(monkeypatch, {"hook_event_name": "UserPromptSubmit", "session_id": "s"}) == 0
    assert sent["spawn"] == [{"op": "stop", "session": "s", "prompt": "", "warm": True}]


def test_disabled_hook_does_nothing(monkeypatch, sent):
    Config(enabled=False).save()
    event = {"hook_event_name": "Stop", "last_assistant_message": "Done."}
    assert run_hook(monkeypatch, event) == 0
    assert sent == {"send": [], "spawn": []}


def test_headless_session_does_nothing(monkeypatch, sent):
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "sdk-cli")
    event = {"hook_event_name": "Stop", "last_assistant_message": "Done."}
    assert run_hook(monkeypatch, event) == 0
    assert sent == {"send": [], "spawn": []}


def test_garbage_stdin_is_ignored(monkeypatch, sent):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert cli.main(["hook"]) == 0
    assert sent == {"send": [], "spawn": []}


def test_off_then_on_persists(sent, capsys, monkeypatch):
    unloaded = []
    monkeypatch.setattr(
        "keryx.summarize.OllamaClient.unload", lambda self: unloaded.append(self.model)
    )
    assert cli.main(["off"]) == 0
    assert Config.load().enabled is False
    assert sent["send"] == [{"op": "quit"}]
    assert unloaded == [Config().model]
    assert cli.main(["on"]) == 0
    assert Config.load().enabled is True
    assert "keryx is on" in capsys.readouterr().out


def test_on_off_never_persists_env_overrides(sent, monkeypatch):
    monkeypatch.setattr("keryx.summarize.OllamaClient.unload", lambda self: None)
    monkeypatch.setenv("KERYX_MODEL", "temporary:1b")
    cli.main(["off"])
    assert Config.load(env=False).model == Config().model


def test_status_without_daemon(sent, capsys):
    assert cli.main(["status"]) == 0
    assert '"daemon": "not running"' in capsys.readouterr().out


def test_unknown_command_prints_usage(capsys):
    assert cli.main(["dance"]) == 2
    assert "keryx hook" in capsys.readouterr().err


def test_every_listed_command_is_in_the_usage_text():
    assert cli.__doc__ is not None
    for cmd in cli.COMMANDS:
        assert cmd in cli.__doc__
