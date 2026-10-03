"""The speech queue: shorten each utterance, synthesize it sentence by sentence, play it.

Shortening has its own thread, so a notice is spoken while a reply waits on the model.
Synthesis runs one sentence ahead of playback, so speech starts after the first
sentence is ready instead of after the whole line. One queue serves every Claude
session on the machine, so sessions never talk over each other.
"""

from __future__ import annotations

import dataclasses
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
from keryx.voices import VoiceSpec, holder

log = logging.getLogger("keryx")

RING = 8  # WAV slots; more than can be queued for playback at once
PLAY_AHEAD = 2
# Other apps come back up after this much quiet, so the music does not pump between lines.
UNDUCK_AFTER = 1.0
LAST_LINES = 64  # holders whose last line can be said again


class Voice(Protocol):
    def synth(self, text: str, voice: VoiceSpec | None = None) -> tuple[np.ndarray, int]: ...
    def has(self, spec: VoiceSpec) -> bool: ...


class Voices(Protocol):
    def assign(self, holder: str, source: str) -> VoiceSpec: ...


class SpeechQueue(Protocol):
    def submit(self, utt: Utterance) -> None: ...
    def stop(self, session: str | None = None) -> None: ...
    def claim(self, holder: str, source: str) -> None: ...
    def knows(self, spec: VoiceSpec) -> bool: ...
    def again(self, holder: str) -> bool: ...
    def close(self, timeout: float = 5.0) -> None: ...
    def idle(self) -> bool: ...


@dataclass
class Utterance:
    text: str
    kind: str = "reply"  # "reply" is shortened first; "notice" is spoken as given
    session: str = ""
    terminal: str = ""  # holds the voice; the session when empty
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
        pronounce: Callable[[str], str] | None = None,
    ):
        """`voices` picks each session's voice; None speaks everything in the default.
        `pronounce` rewrites each sentence just before synthesis."""
        self._shorten = shorten
        self._voices = voices
        self._pronounce = pronounce or (lambda text: text)
        self._last: dict[str, Utterance] = {}  # holder -> its last line, to say again
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
        self._synthesizing = False  # the synth thread holds an utterance
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
            utt.voice = self._voices.assign(holder(utt.terminal, utt.session), utt.source)
        with self._cond:
            (self._to_shorten if utt.kind == "reply" else self._pending).append(utt)
            self._active.append(utt)
            self._cond.notify_all()

    def claim(self, holder: str, source: str) -> None:
        """`holder` started or sent a prompt: hold its voice before it speaks."""
        if self._voices is not None and holder:
            self._voices.assign(holder, source)

    def knows(self, spec: VoiceSpec) -> bool:
        return self._voice.has(spec)

    def stop(self, session: str | None = None) -> None:
        """Cancel queued and playing speech, for one session or (None) all of them."""
        self._cancel(lambda u: session is None or u.session == session)

    def _cancel(self, doomed: Callable[[Utterance], bool]) -> None:
        with self._cond:
            for utt in self._active:
                if doomed(utt):
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

    def _next(self, waiting: list[Utterance], synth: bool = False) -> Utterance | None:
        with self._cond:
            if synth:
                self._synthesizing = False
            while not waiting and not self._closed:
                self._cond.wait()
            if self._closed:
                return None
            if synth:
                self._synthesizing = True  # in the same lock as the pop, so quiet never flickers
            return waiting.pop(0)

    def _quiet(self) -> bool:
        """Nothing left to synthesize or play; a reply still being shortened does not count."""
        with self._cond:
            return not self._pending and not self._synthesizing and self._play_q.empty()

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

    def again(self, holder: str) -> bool:
        """Say `holder`'s last line again in the same voice (anyone's, without a holder)."""
        with self._cond:
            last = self._last.get(holder) if holder else None
            if last is None and not holder and self._last:
                last = next(reversed(self._last.values()))
        if last is None or not last.line:
            return False
        # Cut off what that session is saying now, so the replay is not heard after it; a
        # reply still with the summarizer (no line yet) is kept.
        session = last.session
        self._cancel(lambda u: u.session == session and (u.kind != "reply" or u.line is not None))
        self.submit(dataclasses.replace(last, cancelled=threading.Event()))
        return True

    def _remember(self, utt: Utterance, line: str) -> None:
        if not line:
            return
        with self._cond:
            key = holder(utt.terminal, utt.session)
            self._last.pop(key, None)  # re-insert so the newest comes last
            self._last[key] = Utterance(
                text=line,
                kind="notice",
                session=utt.session,
                terminal=utt.terminal,
                voice=utt.voice,
                line=line,
            )
            while len(self._last) > LAST_LINES:
                self._last.pop(next(iter(self._last)))

    def _synth_loop(self) -> None:
        while (utt := self._next(self._pending, synth=True)) is not None:
            try:
                line = "" if utt.cancelled.is_set() else self._line(utt)
                self._remember(utt, line)
                for sentence in split_sentences(line):
                    if utt.cancelled.is_set():
                        break
                    try:
                        samples, rate = self._voice.synth(self._pronounce(sentence), utt.voice)
                        wav = self._audio_dir / slot_name(next(self._slots))
                        seconds = write_wav(wav, samples, rate)
                    except Exception:  # one bad sentence does not cost the rest of the line
                        log.exception("could not synthesize %r", sentence[:80])
                        continue
                    self.spoken.append(sentence)
                    self._play_q.put((wav, seconds, utt))
            except Exception:
                log.exception("could not synthesize %r", utt.text[:80])
            finally:
                self._play_q.put((None, 0.0, utt))
        self._play_q.put(None)

    def _play_loop(self) -> None:
        ducked = False
        while True:
            try:
                item = self._play_q.get(timeout=UNDUCK_AFTER if ducked else None)
            except queue.Empty:
                if self._quiet():
                    self._safely(self._player.unduck)
                    ducked = False
                continue
            if item is None:
                break
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
            if not ducked:
                self._safely(self._player.duck)
                ducked = True
            try:
                utt.played = self._player.play(wav, seconds, utt.cancelled) or utt.played
            except Exception:
                log.exception("could not play %s", wav)
        if ducked:
            self._safely(self._player.unduck)

    @staticmethod
    def _safely(step: Callable[[], None]) -> None:
        try:
            step()
        except Exception:
            log.exception("could not change other apps' volume")


def slot_name(i: int) -> str:
    return f"keryx-{i}.wav"


def slot_names() -> list[str]:
    return [slot_name(i) for i in range(RING)]
