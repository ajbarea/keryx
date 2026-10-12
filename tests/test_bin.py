import json
import pathlib
import shutil
import subprocess

from keryx import doctor

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_keryx_without_uv_names_the_installer(tmp_path):
    bash = shutil.which("bash")
    assert bash
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    proc = subprocess.run(
        [bash, str(ROOT / "bin" / "keryx"), "status"],
        env={"PATH": str(empty), "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 127
    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" in proc.stderr


def run_without_uv(tmp_path, *args, stdin=""):
    bash = shutil.which("bash")
    assert bash
    empty = tmp_path / "empty-bin"
    empty.mkdir(exist_ok=True)
    return subprocess.run(
        [bash, str(ROOT / "bin" / "keryx"), *args],
        env={"PATH": str(empty), "HOME": str(tmp_path)},
        input=stdin,
        capture_output=True,
        text=True,
    )


def test_session_start_hook_without_uv_tells_the_user(tmp_path):
    proc = run_without_uv(tmp_path, "hook", stdin='{"hook_event_name": "SessionStart"}')
    assert proc.returncode == 0
    message = json.loads(proc.stdout)["systemMessage"]
    assert message == f"keryx needs uv: {doctor.UV_INSTALL}"


def test_other_hooks_without_uv_stay_silent(tmp_path):
    proc = run_without_uv(tmp_path, "hook", stdin='{"hook_event_name": "Stop"}')
    assert proc.returncode == 0
    assert proc.stdout == ""
