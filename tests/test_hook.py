import subprocess

import pytest

from keryx.hook import parse, request_for, source_name


def stop(msg="Done. Tests pass.", **kw):
    return {"hook_event_name": "Stop", "session_id": "s1", "last_assistant_message": msg, **kw}


def test_stop_becomes_a_reply(tmp_path):
    req = request_for(stop(cwd=str(tmp_path)), "cli")
    assert req == {
        "op": "say",
        "kind": "reply",
        "text": "Done. Tests pass.",
        "session": "s1",
        "source": tmp_path.name,
    }


def test_empty_stop_is_silent():
    assert request_for(stop("  "), "cli") is None
    assert request_for(stop(None), "cli") is None


@pytest.mark.parametrize("ep", ["sdk-cli", "sdk-py", "sdk-ts"])
def test_headless_sessions_are_silent(ep):
    assert request_for(stop(), ep) is None


def test_missing_entrypoint_counts_as_interactive():
    assert request_for(stop(), "") is not None


def test_prompt_submit_stops_that_session():
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s9"}
    assert request_for(event, "cli") == {"op": "stop", "session": "s9", "warm": True}


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
