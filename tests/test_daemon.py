import threading
import time

import pytest

from keryx import client
from keryx.config import Config
from keryx.daemon import VERSION, handle, one_at_a_time, request_summary, serve


class FakeSpeaker:
    def __init__(self):
        self.submitted = []
        self.stopped = []
        self.claimed = []
        self.closed = False

    def submit(self, utt):
        self.submitted.append(utt)

    def stop(self, session=None, terminal=""):
        self.stopped.append(session)
        self.stopped_terminals = [*getattr(self, "stopped_terminals", []), terminal]

    def claim(self, holder, source):
        self.claimed.append((holder, source))

    def knows(self, spec):
        return spec.names != ("zz_nope",)

    def again(self, holder):
        self.replays = [*getattr(self, "replays", []), holder]
        return holder == "9:1"

    def close(self, timeout=5.0):
        self.closed = True

    def idle(self):
        return True


def test_handle_say_builds_an_utterance():
    sp = FakeSpeaker()
    reply = handle(
        {"op": "say", "text": "Hi.", "kind": "notice", "session": "s", "source": "r"}, sp
    )
    assert reply == {"ok": True}
    utt = sp.submitted[0]
    assert (utt.text, utt.kind, utt.session, utt.source) == ("Hi.", "notice", "s", "r")


def test_handle_say_carries_an_explicit_voice():
    sp = FakeSpeaker()
    handle({"op": "say", "text": "Hi.", "voice": "af_heart(0.7)+af_bella(0.3)"}, sp)
    assert sp.submitted[0].voice.names == ("af_heart", "af_bella")


@pytest.mark.parametrize("bad", ["af_heart(x)", 5, "a(0)+b(0)", "a(1)+"])
def test_a_bad_voice_is_refused_not_fatal(bad):
    sp = FakeSpeaker()
    assert handle({"op": "say", "text": "Hi.", "voice": bad}, sp)["ok"] is False
    assert sp.submitted == []


def test_a_prompt_and_a_session_start_claim_the_terminals_voice():
    sp = FakeSpeaker()
    handle({"op": "stop", "session": "s1", "prompt": "p", "terminal": "9:1", "source": "r"}, sp)
    handle({"op": "stop", "session": "s3", "source": "r"}, sp)  # outside a terminal
    handle({"op": "warm", "session": "s2", "terminal": "8:1", "source": "q"}, sp, None)
    assert sp.claimed == [("9:1", "r"), ("s3", "r"), ("8:1", "q")]


def test_say_carries_its_terminal():
    sp = FakeSpeaker()
    handle({"op": "say", "text": "Hi.", "session": "s", "terminal": "9:1"}, sp)
    assert sp.submitted[0].terminal == "9:1"


def test_ping_reports_the_version():
    assert handle({"op": "ping"}, FakeSpeaker())["version"] == VERSION


def test_an_unknown_voice_is_refused_before_it_is_queued():
    sp = FakeSpeaker()
    reply = handle({"op": "say", "text": "Hi.", "voice": "zz_nope"}, sp)
    assert reply["ok"] is False and "zz_nope" in reply["error"]
    assert sp.submitted == []


def test_an_unexpected_error_in_a_request_leaves_the_daemon_serving(running, monkeypatch):
    from keryx import daemon

    sock, _, _ = running

    def boom(*a, **k):
        raise RuntimeError("bug")

    monkeypatch.setattr(daemon, "handle", boom)
    assert client.send({"op": "ping"}, sock)["ok"] is False
    monkeypatch.undo()
    assert client.send({"op": "ping"}, sock)["ok"] is True


def test_handle_unknown_kind_is_a_reply():
    sp = FakeSpeaker()
    handle({"op": "say", "text": "Hi.", "kind": "shout"}, sp)
    assert sp.submitted[0].kind == "reply"


def test_handle_rejects_empty_text_and_unknown_ops():
    sp = FakeSpeaker()
    assert handle({"op": "say", "text": "  "}, sp)["ok"] is False
    assert handle({"op": "dance"}, sp)["ok"] is False
    assert sp.submitted == []


def test_handle_stop_with_and_without_session():
    sp = FakeSpeaker()
    handle({"op": "stop", "session": "s1"}, sp)
    handle({"op": "stop"}, sp)
    assert sp.stopped == ["s1", None]


def test_a_stop_names_its_terminal_so_speech_left_by_an_old_session_is_cut():
    sp = FakeSpeaker()
    handle({"op": "stop", "session": "new", "terminal": "9:1"}, sp)
    assert (sp.stopped, sp.stopped_terminals) == (["new"], ["9:1"])


def test_stop_with_warm_loads_the_summarizer():
    sp = FakeSpeaker()
    warmed = threading.Event()
    handle({"op": "stop", "session": "s", "warm": True}, sp, warmed.set)
    assert warmed.wait(2)


def test_stop_without_warm_flag_does_not_warm():
    warmed = threading.Event()
    handle({"op": "stop"}, FakeSpeaker(), warmed.set)
    assert not warmed.wait(0.1)


def test_warm_op_loads_the_summarizer():
    warmed = threading.Event()
    reply = handle({"op": "warm", "version": VERSION}, FakeSpeaker(), warmed.set)
    assert reply == {"ok": True, "version": VERSION}
    assert warmed.wait(2)


def test_warm_without_a_summarizer_is_a_no_op():
    assert handle({"op": "warm"}, FakeSpeaker(), None)["ok"] is True


def test_warm_from_a_newer_version_retires_the_daemon_without_warming():
    warmed = threading.Event()
    sp = FakeSpeaker()
    reply = handle({"op": "warm", "version": "999.0.0"}, sp, warmed.set)
    assert reply["quit"] is True
    assert sp.stopped == [None]
    assert not warmed.wait(0.1)


def test_warm_from_an_older_version_does_not_retire_the_daemon():
    reply = handle({"op": "warm", "version": "0.0.1"}, FakeSpeaker(), None)
    assert reply == {"ok": True, "version": VERSION}


def test_one_at_a_time_skips_calls_while_one_runs():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow():
        calls.append(1)
        entered.set()
        release.wait(2)

    once = one_at_a_time(slow)
    t = threading.Thread(target=once)
    t.start()
    assert entered.wait(2)
    once()  # skipped: the first call is still running
    release.set()
    t.join(2)
    once()  # runs: the first call finished
    assert calls == [1, 1]


class FakePlayer:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_daemon_turned_off_while_starting_exits_before_listening(tmp_path, monkeypatch):
    from keryx import daemon

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.delenv("KERYX_ENABLED", raising=False)
    Config(enabled=False).save()
    sp, player = FakeSpeaker(), FakePlayer()
    monkeypatch.setattr(daemon, "build_speaker", lambda cfg: (sp, player, None))
    sock = tmp_path / "k.sock"
    serve(Config(), sock, idle_exit=0.2, poll=0.05)
    assert not sock.exists()
    assert sp.closed and player.closed


def test_request_summary_omits_text():
    assert request_summary({"op": "say", "source": "r", "text": "secret words"}) == "say r 12 chars"
    assert request_summary(None) == "bad request"


@pytest.fixture
def running(tmp_path):
    sock = tmp_path / "k.sock"
    sp = FakeSpeaker()
    t = threading.Thread(
        target=serve,
        args=(Config(), sock),
        kwargs={"speaker": sp, "idle_exit": 0.2, "poll": 0.05},
        daemon=True,
    )
    t.start()
    deadline = time.time() + 3
    while not sock.exists():
        assert time.time() < deadline
        time.sleep(0.01)
    return sock, sp, t


def test_socket_round_trip(running):
    sock, sp, _ = running
    assert client.send({"op": "ping"}, sock)["ok"] is True
    assert client.send({"op": "say", "text": "Hello."}, sock) == {"ok": True}
    assert sp.submitted[0].text == "Hello."


def test_bad_json_gets_an_error_not_a_crash(running):
    sock, _, _ = running
    import socket as s

    with s.socket(s.AF_UNIX, s.SOCK_STREAM) as c:
        c.connect(str(sock))
        c.sendall(b"{nope")
        c.shutdown(s.SHUT_WR)
        assert b'"ok": false' in client.read_all(c)
    assert client.send({"op": "ping"}, sock)["ok"] is True


def test_idle_daemon_exits_and_cleans_up(running):
    sock, sp, t = running
    t.join(3)
    assert not t.is_alive()
    assert not sock.exists()
    assert sp.closed


def test_send_without_daemon_raises(tmp_path):
    with pytest.raises(OSError):
        client.send({"op": "ping"}, tmp_path / "none.sock")


def test_second_daemon_on_the_same_socket_exits_without_stealing_it(running):
    sock, sp, _ = running
    other = FakeSpeaker()
    started = time.time()
    assert serve(Config(), sock, speaker=other, idle_exit=0.2, poll=0.05) is False
    assert time.time() - started < 1
    assert sock.exists()
    assert client.send({"op": "say", "text": "Still mine."}, sock) == {"ok": True}
    assert sp.submitted[-1].text == "Still mine."
    assert other.submitted == []


def test_quit_stops_speech_and_exits(tmp_path):
    sock = tmp_path / "q.sock"
    sp = FakeSpeaker()
    t = threading.Thread(
        target=serve,
        args=(Config(), sock),
        kwargs={"speaker": sp, "idle_exit": 3600, "poll": 0.05},
        daemon=True,
    )
    t.start()
    deadline = time.time() + 3
    while not sock.exists():
        assert time.time() < deadline
        time.sleep(0.01)
    time.sleep(0.2)
    assert t.is_alive()
    assert client.send({"op": "quit"}, sock)["quit"] is True
    t.join(2)
    assert not t.is_alive()
    assert not sock.exists()


def test_exit_cleanup_deletes_only_keryx_slot_files(tmp_path, monkeypatch):
    from keryx import daemon

    audio = tmp_path / "audio"
    audio.mkdir()
    for name in ("keryx-0.wav", "keryx-7.wav", "song.wav", "0.wav"):
        (audio / name).write_bytes(b"x")
    daemon.remove_slots(audio)
    assert sorted(p.name for p in audio.iterdir()) == ["0.wav", "song.wav"]


def test_a_reply_older_than_the_sessions_latest_prompt_is_dropped():
    sp = FakeSpeaker()
    latest: dict[str, str] = {}

    def say(text, prompt):
        return handle(
            {"op": "say", "text": text, "session": "s", "prompt": prompt}, sp, None, latest
        )

    handle({"op": "stop", "session": "s", "prompt": "p1"}, sp, None, latest)
    assert say("Turn one.", "p1") == {"ok": True}
    handle({"op": "stop", "session": "s", "prompt": "p2"}, sp, None, latest)
    assert say("Turn one, late.", "p1")["dropped"] == "stale"
    assert [u.text for u in sp.submitted] == ["Turn one."]


def test_a_reply_with_no_prompt_history_is_spoken():
    sp = FakeSpeaker()
    handle({"op": "say", "text": "Hi.", "session": "new", "prompt": "p7"}, sp, None, {})
    assert len(sp.submitted) == 1


def test_again_replays_the_terminals_last_line():
    sp = FakeSpeaker()
    assert handle({"op": "again", "terminal": "9:1", "session": "s"}, sp) == {
        "ok": True,
        "replayed": True,
    }
    assert handle({"op": "again", "session": "s"}, sp)["replayed"] is False
    assert sp.replays == ["9:1", "s"]


def test_a_stop_that_does_not_interrupt_still_records_the_prompt():
    sp = FakeSpeaker()
    latest = {}
    handle({"op": "stop", "session": "s", "prompt": "p2", "interrupt": False}, sp, None, latest)
    assert sp.stopped == []
    assert latest == {"s": "p2"}
