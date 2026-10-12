import pathlib
import shutil
import subprocess

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
