"""The speech queue: shorten each utterance, synthesize it sentence by sentence, play it.

Synthesis runs one sentence ahead of playback, so speech starts after the first
sentence is ready instead of after the whole line. One queue serves every Claude
session on the machine, so sessions never talk over each other.
"""

from __future__ import annotations

import itertools
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from keryx.player import Player
from keryx.text import split_sentences
from keryx.voice import write_wav

RING = 8  # WAV slots; more than can be queued for playback at once
PLAY_AHEAD = 2


class Voice(Protocol):
    def synth(self, text: str) -> tuple[np.ndarray, int]: ...


class SpeechQueue(Protocol):
    def submit(self, utt: Utterance) -> None: ...
    def stop(self, session: str | None = None) -> None: ...
    def close(self, timeout: float = 5.0) -> None: ...
    def idle(self) -> bool: ...


@dataclass
class Utterance:
    text: str
    kind: str = "reply"  # "reply" is shortened first; "notice" is spoken as given
    session: str = ""
    source: str = ""
    cancelled: threading.Event = field(default_factory=threading.Event)


class Speaker:
    def __init__(
        self,
        shorten: Callable[[str], str],
        voice: Voice,
        player: Player,
        audio_dir: Path,
    ):
        self._shorten = shorten
        self._voice = voice
        self._player = player
        self._audio_dir = audio_dir
        self._pending: list[Utterance] = []
        self._cond = threading.Condition()
        self._current: Utterance | None = None
        self._playing: Utterance | None = None
        self._last_source = ""
        self._slots = itertools.cycle(range(RING))
        self._play_q: queue.Queue[tuple[Path, float, Utterance] | None] = queue.Queue(PLAY_AHEAD)
        self._closed = False
        self.spoken: list[str] = []  # what was handed to the voice, for logs and tests
        self._threads = [
            threading.Thread(target=self._synth_loop, daemon=True),
            threading.Thread(target=self._play_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def submit(self, utt: Utterance) -> None:
        with self._cond:
            self._pending.append(utt)
            self._cond.notify()

    def stop(self, session: str | None = None) -> None:
        """Cancel queued and playing speech, for one session or (None) all of them."""
        with self._cond:
            for utt in [*self._pending, self._current, self._playing]:
                if utt is not None and (session is None or utt.session == session):
                    utt.cancelled.set()
            self._pending = [u for u in self._pending if not u.cancelled.is_set()]

    def close(self, timeout: float = 5.0) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify()
        for t in self._threads:
            t.join(timeout)

    def idle(self) -> bool:
        with self._cond:
            return (
                not self._pending
                and self._current is None
                and self._playing is None
                and self._play_q.empty()
            )

    def _next(self) -> Utterance | None:
        with self._cond:
            while not self._pending and not self._closed:
                self._cond.wait()
            if self._closed:
                return None
            self._current = self._pending.pop(0)
            return self._current

    def _line(self, utt: Utterance) -> str:
        line = self._shorten(utt.text) if utt.kind == "reply" else utt.text
        if line and utt.source and utt.source != self._last_source:
            line = f"{utt.source}: {line}"
            self._last_source = utt.source
        return line

    def _synth_loop(self) -> None:
        while (utt := self._next()) is not None:
            try:
                line = "" if utt.cancelled.is_set() else self._line(utt)
                for sentence in split_sentences(line):
                    if utt.cancelled.is_set():
                        break
                    samples, rate = self._voice.synth(sentence)
                    wav = self._audio_dir / f"{next(self._slots)}.wav"
                    seconds = write_wav(wav, samples, rate)
                    self.spoken.append(sentence)
                    self._play_q.put((wav, seconds, utt))
            finally:
                with self._cond:
                    self._current = None
        self._play_q.put(None)

    def _play_loop(self) -> None:
        while (item := self._play_q.get()) is not None:
            wav, seconds, utt = item
            with self._cond:
                self._playing = utt
            try:
                if not utt.cancelled.is_set():
                    self._player.play(wav, seconds, utt.cancelled)
            finally:
                with self._cond:
                    self._playing = None
