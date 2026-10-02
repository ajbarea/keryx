"""The speech queue: shorten each utterance, synthesize it sentence by sentence, play it.

Shortening has its own thread, so a notice is spoken while a reply waits on the model.
Synthesis runs one sentence ahead of playback, so speech starts after the first
sentence is ready instead of after the whole line. One queue serves every Claude
session on the machine, so sessions never talk over each other.
"""

from __future__ import annotations

import itertools
import logging
import queue
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from keryx.player import Player
from keryx.text import split_sentences
from keryx.voice import write_wav
from keryx.voices import VoiceSpec

log = logging.getLogger("keryx")

RING = 8  # WAV slots; more than can be queued for playback at once
PLAY_AHEAD = 2


class Voice(Protocol):
    def synth(self, text: str, voice: VoiceSpec | None = None) -> tuple[np.ndarray, int]: ...


class Voices(Protocol):
    def assign(self, session: str, source: str) -> VoiceSpec: ...
    def touch(self, session: str) -> None: ...


class SpeechQueue(Protocol):
    def submit(self, utt: Utterance) -> None: ...
    def stop(self, session: str | None = None) -> None: ...
    def touch(self, session: str) -> None: ...
    def close(self, timeout: float = 5.0) -> None: ...
    def idle(self) -> bool: ...


@dataclass
class Utterance:
    text: str
    kind: str = "reply"  # "reply" is shortened first; "notice" is spoken as given
    session: str = ""
    source: str = ""
    cancelled: threading.Event = field(default_factory=threading.Event)
    line: str | None = None  # the words to say, once shortened
    voice: VoiceSpec | None = None  # None: the configured voice
    announced: bool = False  # its line starts with the source name
    played: bool = False


class Speaker:
    def __init__(
        self,
        shorten: Callable[[str], str],
        voice: Voice,
        player: Player,
        audio_dir: Path,
        voices: Voices | None = None,
    ):
        """`voices` picks each session's voice; None speaks everything in the default."""
        self._shorten = shorten
        self._voices = voices
        self._voice = voice
        self._player = player
        self._audio_dir = audio_dir
        self._cond = threading.Condition()
        self._to_shorten: list[Utterance] = []  # replies waiting for the summarizer
        self._pending: list[Utterance] = []  # waiting for synthesis
        self._active: list[Utterance] = []  # submitted and not yet fully played
        self._last_source = ""
        self._slots = itertools.cycle(range(RING))
        # (wav, seconds, utt) to play, (None, 0, utt) once utt's audio is all queued,
        # None to shut down.
        self._play_q: queue.Queue[tuple[Path | None, float, Utterance] | None] = queue.Queue(
            PLAY_AHEAD
        )
        self._closed = False
        self.spoken: deque[str] = deque(maxlen=50)  # recent sentences, for logs and tests
        self._threads = [
            threading.Thread(target=self._shorten_loop, daemon=True),
            threading.Thread(target=self._synth_loop, daemon=True),
            threading.Thread(target=self._play_loop, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def submit(self, utt: Utterance) -> None:
        if utt.voice is None and self._voices is not None:
            utt.voice = self._voices.assign(utt.session, utt.source)
        with self._cond:
            (self._to_shorten if utt.kind == "reply" else self._pending).append(utt)
            self._active.append(utt)
            self._cond.notify_all()

    def touch(self, session: str) -> None:
        """`session` sent a prompt: it still holds its voice."""
        if self._voices is not None:
            self._voices.touch(session)

    def stop(self, session: str | None = None) -> None:
        """Cancel queued and playing speech, for one session or (None) all of them."""
        with self._cond:
            for utt in self._active:
                if session is None or utt.session == session:
                    utt.cancelled.set()
            waiting = self._to_shorten + self._pending
            dropped = [u for u in waiting if u.cancelled.is_set()]
            self._to_shorten[:] = [u for u in self._to_shorten if not u.cancelled.is_set()]
            self._pending[:] = [u for u in self._pending if not u.cancelled.is_set()]
            # Never synthesized, so no end-of-audio marker will come to retire them.
            for utt in dropped:
                self._active.remove(utt)

    def close(self, timeout: float = 5.0) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        for t in self._threads:
            t.join(timeout)

    def idle(self) -> bool:
        with self._cond:
            return not self._active

    def _next(self, waiting: list[Utterance]) -> Utterance | None:
        with self._cond:
            while not waiting and not self._closed:
                self._cond.wait()
            if self._closed:
                return None
            return waiting.pop(0)

    def _shorten_loop(self) -> None:
        while (utt := self._next(self._to_shorten)) is not None:
            try:
                line = self._shorten(utt.text)
            except Exception:
                log.exception("could not shorten %r", utt.text[:80])
                line = ""
            with self._cond:
                if utt.cancelled.is_set():
                    self._active.remove(utt)
                    continue
                utt.line = line
                self._pending.append(utt)
                self._cond.notify_all()

    def _line(self, utt: Utterance) -> str:
        line = utt.line if utt.line is not None else utt.text
        with self._cond:
            if line and utt.source and utt.source != self._last_source:
                line = f"{utt.source}: {line}"
                self._last_source = utt.source
                utt.announced = True
        return line

    def _synth_loop(self) -> None:
        while (utt := self._next(self._pending)) is not None:
            try:
                line = "" if utt.cancelled.is_set() else self._line(utt)
                for sentence in split_sentences(line):
                    if utt.cancelled.is_set():
                        break
                    samples, rate = self._voice.synth(sentence, utt.voice)
                    wav = self._audio_dir / slot_name(next(self._slots))
                    seconds = write_wav(wav, samples, rate)
                    self.spoken.append(sentence)
                    self._play_q.put((wav, seconds, utt))
            except Exception:
                log.exception("could not synthesize %r", utt.text[:80])
            finally:
                self._play_q.put((None, 0.0, utt))
        self._play_q.put(None)

    def _play_loop(self) -> None:
        while (item := self._play_q.get()) is not None:
            wav, seconds, utt = item
            if wav is None:
                with self._cond:
                    self._active.remove(utt)
                    # Never heard, so the next line from this source must announce it.
                    if utt.announced and not utt.played and self._last_source == utt.source:
                        self._last_source = ""
                continue
            if utt.cancelled.is_set():
                continue
            try:
                utt.played = self._player.play(wav, seconds, utt.cancelled) or utt.played
            except Exception:
                log.exception("could not play %s", wav)


def slot_name(i: int) -> str:
    return f"keryx-{i}.wav"


def slot_names() -> list[str]:
    return [slot_name(i) for i in range(RING)]
