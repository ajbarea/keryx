import pytest


@pytest.fixture(autouse=True)
def outside_a_terminal(monkeypatch):
    """Tests run under a real Claude Code process; keep its pid out of hook requests."""
    monkeypatch.setattr("keryx.hook.terminal_id", lambda: "")
