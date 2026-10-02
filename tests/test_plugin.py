import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_hook_runs_the_bundled_wrapper_async():
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]
    assert set(hooks) == {"Stop", "Notification", "UserPromptSubmit"}
    for groups in hooks.values():
        for group in groups:
            for hook in group["hooks"]:
                assert hook["command"] == '"${CLAUDE_PLUGIN_ROOT}/bin/keryx" hook'
                assert hook["async"] is True


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
