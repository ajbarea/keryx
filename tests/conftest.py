import pytest


@pytest.fixture(autouse=True)
def outside_a_terminal(monkeypatch):
    """Tests run under a real Claude Code process; keep its pid out of hook requests."""
    monkeypatch.setattr("keryx.hook.terminal_id", lambda: "")


@pytest.fixture(autouse=True)
def private_folders(tmp_path_factory, monkeypatch):
    """Keep every test out of the real cache and state folders, which hold the user's logs."""
    root = tmp_path_factory.mktemp("xdg")
    monkeypatch.setenv("XDG_CACHE_HOME", str(root / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(root / "state"))


@pytest.fixture(autouse=True)
def no_keryx_env(monkeypatch):
    """Settings come from the test's own config file: no KERYX_* variable from the shell
    (a fleet session exports KERYX_ENABLED, a user may export KERYX_SPEAK_ONLY)."""
    import os

    for key in [k for k in os.environ if k.startswith("KERYX_")]:
        monkeypatch.delenv(key)
