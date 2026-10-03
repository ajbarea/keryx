import subprocess

import pytest

from keryx import version
from keryx.hook import parse, request_for, source_name


def stop(msg="Done. Tests pass.", **kw):
    return {
        "hook_event_name": "Stop",
        "session_id": "s1",
        "prompt_id": "p1",
        "last_assistant_message": msg,
        **kw,
    }


def test_stop_becomes_a_reply(tmp_path):
    req = request_for(stop(cwd=str(tmp_path)), "cli")
    assert req == {
        "op": "say",
        "kind": "reply",
        "text": "Done. Tests pass.",
        "session": "s1",
        "prompt": "p1",
        "terminal": "",
        "source": tmp_path.name,
    }


def test_every_request_names_its_terminal(monkeypatch):
    monkeypatch.setattr("keryx.hook.terminal_id", lambda: "42:7")
    events = [
        stop(),
        {"hook_event_name": "UserPromptSubmit", "session_id": "s"},
        {"hook_event_name": "SessionStart", "session_id": "s"},
        {
            "hook_event_name": "Notification",
            "notification_type": "permission_prompt",
            "message": "Claude needs your permission",
        },
    ]
    for event in events:
        request = request_for(event, "cli")
        assert request is not None and request["terminal"] == "42:7"


def test_empty_stop_is_silent():
    assert request_for(stop("  "), "cli") is None
    assert request_for(stop(None), "cli") is None


@pytest.mark.parametrize("ep", ["sdk-cli", "sdk-py", "sdk-ts"])
def test_headless_sessions_are_silent(ep):
    assert request_for(stop(), ep) is None


def test_missing_entrypoint_counts_as_interactive():
    assert request_for(stop(), "") is not None


def test_prompt_submit_stops_that_session():
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s9", "prompt_id": "p9"}
    expected = {
        "op": "stop",
        "session": "s9",
        "prompt": "p9",
        "terminal": "",
        "source": "",
        "warm": True,
    }
    assert request_for(event, "cli") == expected


def test_prompt_submit_names_its_repo_so_the_session_can_hold_a_voice(tmp_path):
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": str(tmp_path)}
    request = request_for(event, "cli")
    assert request is not None
    assert request["source"] == tmp_path.name


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact"])
def test_session_start_warms(source):
    event = {"hook_event_name": "SessionStart", "session_id": "s", "source": source}
    expected = {"op": "warm", "version": version(), "session": "s", "terminal": "", "source": ""}
    assert request_for(event, "cli") == expected


def test_headless_session_start_is_silent():
    assert request_for({"hook_event_name": "SessionStart"}, "sdk-cli") is None


# Claude Code sends the text as `prompt` (seen live, 2026-10-02); the docs say `user_input`.
@pytest.mark.parametrize("field", ["prompt", "user_input"])
def test_keryx_commands_do_not_wake_the_daemon(field):
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s", field: "/keryx:off"}
    assert request_for(event, "cli") is None


def test_permission_prompt_is_spoken_in_first_person():
    event = {
        "hook_event_name": "Notification",
        "session_id": "s1",
        "notification_type": "permission_prompt",
        "message": "Claude needs your permission to use Bash",
    }
    req = request_for(event, "cli")
    assert req is not None
    assert req["kind"] == "notice"
    assert req["text"] == "I need your permission to use Bash"


@pytest.mark.parametrize("kind", ["idle_prompt", "auth_success", "agent_completed"])
def test_other_notifications_are_silent(kind):
    event = {"hook_event_name": "Notification", "notification_type": kind, "message": "x"}
    assert request_for(event, "cli") is None


def test_subagent_stop_is_silent():
    assert (
        request_for({"hook_event_name": "SubagentStop", "last_assistant_message": "x"}, "cli")
        is None
    )


def test_source_name_uses_main_checkout_for_worktrees(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
    wt = repo / ".claude" / "worktrees" / "feature"
    subprocess.run([*git, "-C", str(repo), "worktree", "add", "-q", str(wt)], check=True)
    assert source_name(str(wt)) == "myrepo"
    assert source_name(str(repo)) == "myrepo"


def test_source_name_from_a_subfolder_is_the_repo(tmp_path):
    (tmp_path / "myrepo" / ".git").mkdir(parents=True)
    (tmp_path / "myrepo" / "src" / "pkg").mkdir(parents=True)
    assert source_name(str(tmp_path / "myrepo" / "src" / "pkg")) == "myrepo"


def test_source_name_of_a_submodule_is_its_own_folder(tmp_path):
    sub = tmp_path / "outer" / "vendor" / "lib"
    sub.mkdir(parents=True)
    (tmp_path / "outer" / ".git" / "modules" / "lib").mkdir(parents=True)
    (sub / ".git").write_text("gitdir: ../../.git/modules/lib\n")
    assert source_name(str(sub)) == "lib"


def test_source_name_never_runs_git(tmp_path, monkeypatch):
    import subprocess as sp

    def no_git(*a, **k):
        raise AssertionError("ran a subprocess")

    monkeypatch.setattr(sp, "run", no_git)
    monkeypatch.setattr(sp, "Popen", no_git)
    (tmp_path / "r" / ".git").mkdir(parents=True)
    assert source_name(str(tmp_path / "r")) == "r"


def test_source_name_outside_git_is_the_folder(tmp_path):
    assert source_name(str(tmp_path)) == tmp_path.name
    assert source_name("") == ""


def test_parse_tolerates_garbage():
    assert parse("not json") == {}
    assert parse("[1]") == {}
    assert parse('{"a": 1}') == {"a": 1}


@pytest.mark.parametrize("ep", ["claude-vscode", "claude-desktop", "cli"])
def test_interactive_surfaces_speak(ep):
    assert request_for(stop(), ep) is not None


def test_silent_events_do_not_walk_the_process_tree(monkeypatch):
    def walked():
        raise AssertionError("walked /proc for nothing")

    monkeypatch.setattr("keryx.hook.terminal_id", walked)
    assert request_for(stop("  "), "cli") is None
    assert request_for({"hook_event_name": "SubagentStop"}, "cli") is None
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": "/keryx:off"}
    assert request_for(event, "cli") is None


REPLAY_PHRASES = [
    "say that again",
    "Say that again.",
    "sorry, say that again please",
    "can you repeat that?",
    "Repeat yourself",
    "come again?",
    "What did you just say?",
    "I didn't catch that",
    "I didn\u2019t hear you",
    "pardon?",
    "  hey claude, say it once more  ",
    "say that once more",
]


@pytest.mark.parametrize("prompt", REPLAY_PHRASES)
def test_replay_requests_are_recognized(prompt):
    from keryx.hook import is_replay

    assert is_replay(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "say that again in Spanish",
        "repeat that test run",
        "why did you say that?",
        "fix the again function",
        "say that again but shorter",
        "",
    ],
)
def test_anything_more_goes_to_claude(prompt):
    from keryx.hook import is_replay

    assert not is_replay(prompt)


def test_a_replay_request_holds_back_what_only_a_real_turn_needs():
    event = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s",
        "prompt_id": "p2",
        "prompt": "say that again",
    }
    request = request_for(event, "cli")
    # No prompt id: an answered replay starts no turn, so the earlier reply is not stale.
    # No warm: nothing is coming for the summarizer.
    assert request is not None
    assert request["interrupt"] is False
    assert "prompt" not in request and "warm" not in request


def test_a_replay_phrase_in_user_input_is_held_back_too():
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "user_input": "pardon?"}
    request = request_for(event, "cli")
    assert request is not None and request["interrupt"] is False


def test_a_replay_phrase_in_a_headless_session_is_not_a_replay_event():
    from keryx.hook import is_replay_event

    event = {"prompt": "say that again"}
    assert is_replay_event(event, "cli")
    assert not is_replay_event(event, "sdk-cli")


def test_a_long_prompt_is_never_a_replay_request():
    from keryx.hook import MAX_REPLAY_CHARS, is_replay

    assert is_replay("hey, " * 5 + "say that again")
    assert not is_replay("hey, " * 20 + "say that again")
    assert not is_replay("say that again" + " " * MAX_REPLAY_CHARS)


def test_an_ordinary_prompt_interrupts():
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "prompt": "fix it"}
    request = request_for(event, "cli")
    assert request is not None and "interrupt" not in request


def test_a_curly_apostrophe_is_still_a_replay_request():
    from keryx.hook import is_replay

    assert is_replay("I didn\u2019t catch that")
