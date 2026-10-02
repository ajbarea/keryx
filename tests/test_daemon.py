import threading
import time

import pytest

from keryx import client
from keryx.config import Config
from keryx.daemon import handle, request_summary, serve


class FakeSpeaker:
    def __init__(self):
        self.submitted = []
        self.stopped = []
        self.closed = False

    def submit(self, utt):
        self.submitted.append(utt)

    def stop(self, session=None):
        self.stopped.append(session)

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


def test_stop_with_warm_loads_the_summarizer():
    sp = FakeSpeaker()
    warmed = threading.Event()
    handle({"op": "stop", "session": "s", "warm": True}, sp, warmed.set)
    assert warmed.wait(2)


def test_stop_without_warm_flag_does_not_warm():
    warmed = threading.Event()
    handle({"op": "stop"}, FakeSpeaker(), warmed.set)
    assert not warmed.wait(0.1)


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
    serve(Config(), sock, speaker=other, idle_exit=0.2, poll=0.05)
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
