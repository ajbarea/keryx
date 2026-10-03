import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


REPLAY = '"${CLAUDE_PLUGIN_ROOT}/bin/keryx-replay"'


def test_every_hook_runs_the_bundled_wrapper_async_except_the_replay():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {"SessionStart", "Stop", "Notification", "UserPromptSubmit"}
    commands = []
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                commands.append(hook["command"])
                if hook["command"] == REPLAY:
                    assert "async" not in hook  # it must block a prompt it answers
                    assert hook["timeout"] <= 10
                else:
                    assert hook["command"] == '"${CLAUDE_PLUGIN_ROOT}/bin/keryx" hook'
                    assert hook["async"] is True
    assert commands.count(REPLAY) == 1


def test_the_replay_screen_is_executable():
    assert os.access(ROOT / "bin" / "keryx-replay", os.X_OK)


def test_notification_matcher_matches_what_the_hook_speaks():
    from keryx.hook import SPOKEN_NOTIFICATIONS

    (group,) = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["Notification"]
    assert set(group["matcher"].split("|")) == SPOKEN_NOTIFICATIONS


def test_wrapper_is_executable():
    assert os.access(ROOT / "bin" / "keryx", os.X_OK)


def test_skills_call_existing_commands():
    from keryx import __main__ as cli

    for skill in (ROOT / "skills").glob("*/SKILL.md"):
        cmd = re.search(r"!`keryx (\w+)`", skill.read_text())
        assert cmd, skill
        assert cmd.group(1) in cli.COMMANDS


def test_manifest_versions_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    project = (ROOT / "pyproject.toml").read_text()
    assert f'version = "{plugin["version"]}"' in project


def screen(tmp_path, prompt):
    """Run bin/keryx-replay with a stand-in `keryx` that records it was reached."""
    import shutil
    import subprocess

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    shutil.copy(ROOT / "bin" / "keryx-replay", bin_dir / "keryx-replay")
    marker = tmp_path / "reached"
    (bin_dir / "keryx").write_text(f"#!/bin/sh\ncat > /dev/null; touch {marker}\n")
    os.chmod(bin_dir / "keryx", 0o755)
    event = json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt})
    done = subprocess.run([str(bin_dir / "keryx-replay")], input=event, text=True, check=False)
    reached = marker.exists()
    marker.unlink(missing_ok=True)
    return done.returncode, reached


def test_the_screen_passes_short_replay_like_prompts_to_python(tmp_path):
    assert screen(tmp_path, "Say that again.") == (0, True)
    assert screen(tmp_path, "sorry, I didn't catch that") == (0, True)


def test_the_screen_turns_away_other_prompts_without_python(tmp_path):
    assert screen(tmp_path, "refactor the parser") == (0, False)
    long_prompt = "please read every file in the repo and then say that again " * 3
    assert screen(tmp_path, long_prompt) == (0, False)


def test_the_screen_and_the_matcher_share_one_word_list():
    from keryx.hook import SCREEN_WORDS

    script = (ROOT / "bin" / "keryx-replay").read_text()
    assert f"words='{'|'.join(SCREEN_WORDS)}'" in script


def test_every_phrase_the_matcher_takes_gets_past_the_screen(tmp_path):
    from test_hook import REPLAY_PHRASES

    for phrase in REPLAY_PHRASES:
        assert screen(tmp_path, phrase) == (0, True), phrase
