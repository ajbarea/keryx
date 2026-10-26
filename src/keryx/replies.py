"""Keep each session's latest spoken reply as one clip, for klepsydra's wall to play again.

Contract: docs/reply-clips.md. Every failure is logged at debug and swallowed; speech never
waits on or fails because of these files.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import numpy as np

from keryx.voice import write_wav

log = logging.getLogger("keryx")

FOLDER = "replies"
KEEP = 32  # clips kept, newest first; klepsydra shows far fewer sessions than this
GAP = 0.25  # seconds of silence between sentences, as the player leaves between clips
STALE_TMP = 60.0  # seconds before another run's temp file counts as litter
SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
CLIP = re.compile(rf"({SESSION.pattern})\.wav")
TMP = re.compile(rf"tmp-\d+-{SESSION.pattern}\.wav")


def replies_dir(fleet: Path | None) -> Path | None:
    """The clips' folder: `replies/` beside klepsydra's `fleet/`."""
    return None if fleet is None else fleet.parent / FOLDER


class ReplyClips:
    def __init__(self, folder: Path | None, enabled: bool = True, keep: int = KEEP):
        """`folder` is `replies_dir(fleet_dir())`; nothing is written unless klepsydra's
        `fleet/` beside it is a real folder."""
        self._folder = folder
        self._enabled = enabled
        self._keep = keep

    def save(self, session: str, sentences: list[tuple[np.ndarray, int]]) -> None:
        """Write `sentences` (samples and rate, in order) as `session`'s one clip, replacing
        its last, then drop all but the newest `keep` clips. No sentences removes the
        session's clip, which an older reply would otherwise stand in for."""
        folder = self._folder
        if not (self._enabled and folder and SESSION.fullmatch(session)):
            return
        tmp = folder / f"tmp-{os.getpid()}-{session}.wav"
        try:
            fleet = folder.parent / "fleet"
            if fleet.is_symlink() or not fleet.is_dir() or folder.is_symlink():
                return
            if not sentences:
                (folder / f"{session}.wav").unlink(missing_ok=True)
                return
            folder.mkdir(exist_ok=True)
            rate = sentences[0][1]
            gap = np.zeros(round(rate * GAP), dtype=np.float32)
            parts: list[np.ndarray] = []
            # Kokoro has one rate; a sentence at another would play at the wrong pitch.
            for samples, r in sentences:
                if r != rate:
                    continue
                if parts:
                    parts.append(gap)
                parts.append(np.asarray(samples, dtype=np.float32))
            write_wav(tmp, np.concatenate(parts), rate)
            os.replace(tmp, folder / f"{session}.wav")
            self._prune(folder)
        except Exception as exc:
            log.debug("could not keep %s's reply: %s", session, exc)
            tmp.unlink(missing_ok=True)

    def _prune(self, folder: Path) -> None:
        clips: list[tuple[float, Path]] = []
        now = time.time()
        for entry in os.scandir(folder):
            try:
                if CLIP.fullmatch(entry.name) and entry.is_file(follow_symlinks=False):
                    clips.append((entry.stat().st_mtime, Path(entry.path)))
                elif TMP.fullmatch(entry.name) and now - entry.stat().st_mtime > STALE_TMP:
                    os.unlink(entry.path)
            except OSError as exc:
                log.debug("could not prune %s: %s", entry.name, exc)
        clips.sort(reverse=True)
        for _, path in clips[self._keep :]:
            path.unlink(missing_ok=True)
