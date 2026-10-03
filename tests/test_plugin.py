import json
import os
import re
from pathlib import Path

import pytest

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


def test_the_screen_never_turns_away_what_the_matcher_takes(tmp_path):
    from keryx.hook import MAX_REPLAY_CHARS, is_replay

    word = "again"
    longest_front = "okay, " * 7 + "say that " + word  # the word as late as it can come
    longest_back = "come " + word + " " * (MAX_REPLAY_CHARS - 10)  # and as early
    for phrase in (longest_front, longest_back):
        assert len(phrase) <= MAX_REPLAY_CHARS and is_replay(phrase), phrase
        assert screen(tmp_path, phrase) == (0, True), phrase


def test_the_screen_caps_are_the_matchers_cap_plus_its_slack():
    from keryx.hook import MAX_REPLAY_CHARS, SCREEN_SLACK

    script = (ROOT / "bin" / "keryx-replay").read_text()
    cap = MAX_REPLAY_CHARS + SCREEN_SLACK
    assert f'[^"]{{0,{cap}}}(\'"$words"\')[^"]{{0,{cap}}}"' in script


def test_the_screen_reads_user_input_as_the_matcher_does(tmp_path):
    import subprocess

    marker = tmp_path / "reached"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    import shutil

    shutil.copy(ROOT / "bin" / "keryx-replay", bin_dir / "keryx-replay")
    (bin_dir / "keryx").write_text(f"#!/bin/sh\ncat > /dev/null; touch {marker}\n")
    os.chmod(bin_dir / "keryx", 0o755)
    event = json.dumps({"hook_event_name": "UserPromptSubmit", "user_input": "say that again"})
    subprocess.run([str(bin_dir / "keryx-replay")], input=event, text=True, check=True)
    assert marker.exists()


def test_every_third_party_import_is_a_declared_dependency():
    import ast
    import sys
    import tomllib

    declared = {
        re.split(r"[<>=\[ ;]", dep, maxsplit=1)[0].lower().replace("_", "-")
        for dep in tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    }
    provides = {"kokoro_onnx": "kokoro-onnx", "onnxruntime": "onnxruntime-gpu"}
    imported = set()
    for source in (ROOT / "src" / "keryx").glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
    outside = imported - set(sys.stdlib_module_names) - {"keryx"}
    missing = {provides.get(m, m).lower().replace("_", "-") for m in outside} - declared
    assert not missing


def run_wrapper(tmp_path, version, name="plugin"):
    """Run a copy of bin/keryx as plugin `name` at `version`, with a stand-in `uv` that prints
    the venv it was told to use. Returns (that venv, the cache's keryx dir)."""
    import shutil
    import subprocess

    root = tmp_path / name
    (root / "bin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin").mkdir(exist_ok=True)
    shutil.copy(ROOT / "bin" / "keryx", root / "bin" / "keryx")
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": version}))
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    (tools / "uv").write_text('#!/bin/sh\necho "$UV_PROJECT_ENVIRONMENT"\n')
    os.chmod(tools / "uv", 0o755)
    cache = tmp_path / "cache"
    env = {
        "PATH": f"{tools}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "XDG_CACHE_HOME": str(cache),
    }
    done = subprocess.run(
        [str(root / "bin" / "keryx"), "status"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(done.stdout.strip()), cache / "keryx"


def test_each_plugin_version_gets_its_own_venv(tmp_path):
    old, base = run_wrapper(tmp_path, "0.5.0")
    new, _ = run_wrapper(tmp_path, "0.5.1")
    assert old != new and old.parent == new.parent == base
    assert old.name.startswith("venv-0.5.0-") and new.name.startswith("venv-0.5.1-")
    assert run_wrapper(tmp_path, "0.5.1")[0] == new  # stable between runs


def test_the_same_version_in_another_checkout_does_not_share_a_venv(tmp_path):
    here, _ = run_wrapper(tmp_path, "0.5.1", "one")
    there, _ = run_wrapper(tmp_path, "0.5.1", "two")
    assert here != there


def test_a_venv_whose_checkout_is_removed_is_pruned_and_nothing_else_is(tmp_path):
    import shutil

    stale, base = run_wrapper(tmp_path, "0.4.0", "old")
    stale.mkdir(parents=True)
    kept, _ = run_wrapper(tmp_path, "0.5.0", "kept")
    kept.mkdir(parents=True)
    legacy, review = base / "venv", base / "venv-review"  # not named by the wrapper
    legacy.mkdir()
    review.mkdir()
    shutil.rmtree(tmp_path / "old")
    current, _ = run_wrapper(tmp_path, "0.5.1", "new")
    assert not stale.exists() and not (base / f"{stale.name}.root").exists()
    assert kept.exists() and legacy.exists() and review.exists()
    assert current.parent == base


def test_a_venv_that_cannot_be_deleted_does_not_stop_keryx(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root deletes anything")
    import shutil

    stale, base = run_wrapper(tmp_path, "0.4.0", "old")
    (stale / "inner").mkdir(parents=True)
    (stale / "inner" / "f").write_text("x")
    (stale / "inner").chmod(0o500)  # its files cannot be unlinked
    shutil.rmtree(tmp_path / "old")
    try:
        current, _ = run_wrapper(tmp_path, "0.5.1", "new")  # check=True: must still reach uv
        assert current.parent == base
    finally:
        (stale / "inner").chmod(0o700)
