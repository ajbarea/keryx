import io
import json

import pytest

from keryx import __main__ as cli
from keryx import client, version
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
    monkeypatch.setattr(
        client,
        "send_or_spawn",
        lambda req, *a, **k: calls["spawn"].append(req) or {"ok": True, "version": version()},
    )
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
    assert sent["spawn"] == [
        {"op": "stop", "session": "s", "prompt": "", "terminal": "", "source": "", "warm": True}
    ]


def test_session_start_spawns_and_warms(monkeypatch, sent):
    assert run_hook(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s"}) == 0
    assert sent["spawn"] == [
        {"op": "warm", "version": version(), "session": "s", "terminal": "", "source": ""}
    ]


class ExitedDaemon:
    def __init__(self, status=0):
        self.status = status

    def poll(self):
        return self.status


def test_a_spawned_daemon_that_exits_is_not_waited_on(monkeypatch):
    def no_socket(req, *a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(client, "send", no_socket)
    monkeypatch.setattr(client, "spawn", ExitedDaemon)
    with pytest.raises(FileNotFoundError):
        client.send_or_spawn({"op": "warm"}, wait=30)


def test_a_daemon_that_lost_the_lock_to_a_retiring_one_is_spawned_again(monkeypatch):
    spawned = []
    sends = iter([FileNotFoundError, FileNotFoundError, FileNotFoundError, {"ok": True}])

    def send(req, *a, **k):
        out = next(sends)
        if out is FileNotFoundError:
            raise out
        return out

    def spawn():
        spawned.append(1)
        return ExitedDaemon(client.LOCK_BUSY_EXIT if len(spawned) == 1 else None)

    monkeypatch.setattr(client, "send", send)
    monkeypatch.setattr(client, "spawn", spawn)
    assert client.send_or_spawn({"op": "warm"}, wait=30) == {"ok": True}
    assert len(spawned) == 2


@pytest.mark.parametrize(
    "reply",
    [
        {"ok": False, "error": "unknown op 'warm'"},  # a 0.1.0 daemon
        {"ok": True, "version": "0.0.9"},
        {"ok": True, "quit": True, "version": "0.0.9"},
    ],
)
def test_session_start_replaces_a_daemon_from_another_version(monkeypatch, reply):
    calls = []
    monkeypatch.setattr(client, "send_or_spawn", lambda req, *a, **k: reply)
    monkeypatch.setattr(client, "replace_daemon", lambda req, rep: calls.append(rep))
    assert run_hook(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s"}) == 0
    assert calls == [reply]


def test_session_start_keeps_a_current_daemon(monkeypatch):
    calls = []
    monkeypatch.setattr(
        client, "send_or_spawn", lambda req, *a, **k: {"ok": True, "version": version()}
    )
    monkeypatch.setattr(client, "replace_daemon", lambda req, rep: calls.append(rep))
    assert run_hook(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s"}) == 0
    assert calls == []


def test_replace_daemon_quits_the_old_one_waits_for_its_socket_then_respawns(tmp_path, monkeypatch):
    sock = tmp_path / "k.sock"
    sock.touch()
    sent, respawned = [], []

    def send(req, path=None, *a, **k):
        sent.append(req)
        sock.unlink()  # the old daemon exits on quit
        return {"ok": True, "quit": True}

    monkeypatch.setattr(client, "send", send)
    monkeypatch.setattr(client, "send_or_spawn", lambda req, *a, **k: respawned.append(req))
    client.replace_daemon({"op": "warm", "version": "v"}, {"ok": False}, sock)
    assert sent == [{"op": "quit"}]
    assert respawned == [{"op": "warm", "version": "v"}]


def test_replace_daemon_does_not_quit_a_daemon_already_retiring(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(client, "send", lambda req, *a, **k: sent.append(req))
    monkeypatch.setattr(client, "send_or_spawn", lambda req, *a, **k: None)
    client.replace_daemon({"op": "warm"}, {"ok": True, "quit": True}, tmp_path / "gone.sock")
    assert sent == []


def test_hook_with_no_daemon_to_answer_exits_quietly(monkeypatch):
    def no_daemon(req, *a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(client, "send_or_spawn", no_daemon)
    event = {"hook_event_name": "Stop", "session_id": "s", "last_assistant_message": "Done."}
    assert run_hook(monkeypatch, event) == 0


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


@pytest.mark.parametrize("arg", ["all", "-1", "0", "\u00b2"])
def test_voices_refuses_a_bad_count(arg, sent, capsys):
    assert cli.main(["voices", arg]) == 2
    assert sent["spawn"] == []
    assert "usage" in capsys.readouterr().err


def test_voices_plays_the_first_n_on_a_current_daemon(sent):
    assert cli.main(["voices", "3"]) == 0
    assert sent["spawn"][0] == {"op": "ping", "version": version()}
    assert [r["voice"] for r in sent["spawn"][1:]] == ["af_heart", "am_michael", "bf_emma"]


def test_voices_reports_a_refused_voice(monkeypatch, capsys):
    monkeypatch.setattr(
        client,
        "send_or_spawn",
        lambda req, *a, **k: (
            {"ok": True, "version": version()}
            if req["op"] == "ping"
            else {"ok": False, "error": "unknown voice"}
        ),
    )
    assert cli.main(["voices", "1"]) == 0
    assert "unknown voice" in capsys.readouterr().err


def test_voices_while_off_says_so_and_starts_nothing(sent, capsys):
    Config(enabled=False).save()
    assert cli.main(["voices"]) == 1
    assert sent == {"send": [], "spawn": []}
    assert "off" in capsys.readouterr().err


def test_voices_without_a_daemon_reports_it(monkeypatch, capsys):
    def no_daemon(req, *a, **k):
        raise ConnectionRefusedError("refused")

    monkeypatch.setattr(client, "send_or_spawn", no_daemon)
    assert cli.main(["voices", "1"]) == 1
    assert "did not answer" in capsys.readouterr().err


def test_voices_speaks_readable_names(sent):
    cli.main(["voices", "1"])
    assert sent["spawn"][1]["text"] == "Voice 1, heart."


def test_every_listed_command_is_in_the_usage_text():
    assert cli.__doc__ is not None
    for cmd in cli.COMMANDS:
        assert cmd in cli.__doc__


def test_a_newer_daemon_is_kept(monkeypatch):
    calls = []
    monkeypatch.setattr(
        client, "send_or_spawn", lambda req, *a, **k: {"ok": True, "version": "999.0.0"}
    )
    monkeypatch.setattr(client, "replace_daemon", lambda req, rep: calls.append(rep))
    assert run_hook(monkeypatch, {"hook_event_name": "SessionStart", "session_id": "s"}) == 0
    assert calls == []


@pytest.mark.parametrize(
    ("theirs", "ours", "expected"),
    [
        ("0.1.1", "0.2.0", True),
        ("0.2.0", "0.2.0", False),
        ("0.10.0", "0.9.0", False),
        (None, "0.2.0", True),
        ("garbage", "0.2.0", True),
    ],
)
def test_older(theirs, ours, expected):
    from keryx import older

    assert older(theirs, ours) is expected
