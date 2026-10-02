import os
from pathlib import Path

from keryx.procs import is_alive, terminal_id


def fake_proc(tmp_path, procs):
    """procs: {pid: (comm, ppid, starttime, argv)} laid out like /proc."""
    for pid, (comm, ppid, start, argv) in procs.items():
        d = tmp_path / str(pid)
        d.mkdir()
        # stat fields after the name: state ppid ... with starttime as field 22
        rest = ["S", str(ppid)] + ["0"] * 17 + [str(start)]
        (d / "stat").write_text(f"{pid} ({comm}) {' '.join(rest)}\n")
        (d / "comm").write_text(comm + "\n")
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    return tmp_path


def test_the_nearest_claude_ancestor_is_the_terminal(tmp_path):
    proc = fake_proc(
        tmp_path,
        {
            50: ("python3", 40, 900, ["python3", "-m", "keryx", "hook"]),
            40: ("sh", 30, 800, ["sh", "-c", "keryx hook"]),
            30: ("claude", 20, 700, ["claude", "-p"]),  # a nested `claude -p`
            20: ("bash", 10, 600, ["bash"]),
            10: ("claude", 1, 500, ["claude"]),
        },
    )
    assert terminal_id(50, proc) == "30:700"


def test_an_npm_install_is_found_by_its_command_line(tmp_path):
    cli = "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"
    proc = fake_proc(tmp_path, {50: ("sh", 30, 900, ["sh"]), 30: ("node", 1, 700, ["node", cli])})
    assert terminal_id(50, proc) == "30:700"


def test_a_script_merely_mentioning_claude_is_not_a_terminal(tmp_path):
    proc = fake_proc(
        tmp_path,
        {50: ("sh", 30, 900, ["sh"]), 30: ("python3", 1, 700, ["python3", "-c", "claude"])},
    )
    assert terminal_id(50, proc) == ""


def test_outside_claude_there_is_no_terminal(tmp_path):
    proc = fake_proc(tmp_path, {50: ("sh", 20, 900, ["sh"]), 20: ("bash", 1, 600, ["bash"])})
    assert terminal_id(50, proc) == ""


def test_a_name_with_spaces_and_parentheses_still_parses(tmp_path):
    proc = fake_proc(
        tmp_path, {50: ("a (b) c", 30, 900, ["x"]), 30: ("claude", 1, 700, ["claude"])}
    )
    assert terminal_id(50, proc) == "30:700"


def test_a_running_terminal_is_alive_and_a_reused_pid_is_not(tmp_path):
    proc = fake_proc(tmp_path, {30: ("claude", 1, 700, ["claude"])})
    assert is_alive("30:700", proc) is True
    assert is_alive("30:699", proc) is False  # same pid, another process
    assert is_alive("31:700", proc) is False  # gone


def test_a_bare_session_id_is_not_a_terminal(tmp_path):
    assert is_alive("4f1c-session-id", tmp_path) is None
    assert is_alive("", tmp_path) is None


def test_this_process_is_alive():
    fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
    assert is_alive(f"{os.getpid()}:{fields[19]}") is True


def test_claude_running_as_pid_1_is_the_terminal(tmp_path):
    proc = fake_proc(tmp_path, {50: ("sh", 1, 900, ["sh"]), 1: ("claude", 0, 5, ["claude"])})
    assert terminal_id(50, proc) == "1:5"


def test_a_zombie_is_not_alive(tmp_path):
    proc = fake_proc(tmp_path, {30: ("claude", 1, 700, ["claude"])})
    stat = tmp_path / "30" / "stat"
    stat.write_text(stat.read_text().replace(") S ", ") Z "))
    assert is_alive("30:700", proc) is False
