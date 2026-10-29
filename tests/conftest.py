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
