"""A distinct voice for each Claude Code session, kept per repo across restarts.

A repo keeps the voice it was first given unless another active session is using it;
then, like a second session in the same repo, it borrows the next voice nobody active
is using. Past the stock voices come same-gender blends, so voices only repeat once
every blend is taken too. Homes and holds are saved, so a daemon restart changes nobody's
voice.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Kokoro v1.0's English voices graded C or better in its VOICES.md (research 2026-10),
# ordered so neighbours differ in accent or gender, best grades first.
POOL = (
    "af_heart",  # A
    "am_michael",  # C+
    "bf_emma",  # B-
    "bm_george",  # C
    "af_bella",  # A-
    "am_fenrir",  # C+
    "bf_isabella",  # C
    "bm_fable",  # C
    "af_nicole",  # B-
    "am_puck",  # C+
    "af_aoede",  # C+
    "af_kore",  # C+
    "af_sarah",  # C+
    "af_alloy",  # C
    "af_nova",  # C
)

LANG = {"a": "en-us", "b": "en-gb"}

# Blends of voices far apart (another gender) come out muddy, so only same-gender pairs.
BLEND_WEIGHTS = ((0.5, 0.5), (0.7, 0.3), (0.3, 0.7))

# A session silent this long no longer holds its voice.
ACTIVE_SECONDS = 30 * 60
# A repo silent this long stops reserving its home voice.
HOME_SECONDS = 14 * 24 * 3600


@dataclass(frozen=True)
class VoiceSpec:
    names: tuple[str, ...]
    weights: tuple[float, ...] = (1.0,)

    def __post_init__(self):
        if not self.names or not all(self.names) or len(self.weights) != len(self.names):
            raise ValueError(f"{len(self.names)} voices with {len(self.weights)} weights")
        if not all(math.isfinite(w) and w > 0 for w in self.weights):
            raise ValueError(f"weights must be positive: {self.weights}")

    @property
    def lang(self) -> str:
        return LANG.get(self.names[0][0], "en-us")

    @classmethod
    def parse(cls, label: object) -> VoiceSpec:
        """Inverse of `label`: `af_heart` or `af_heart(0.7)+af_bella(0.3)`; else ValueError."""
        if not isinstance(label, str):
            raise ValueError(f"not a voice label: {label!r}")
        names, weights = [], []
        for part in label.split("+"):
            name, _, weight = part.partition("(")
            names.append(name.strip())
            weights.append(float(weight.removesuffix(")")) if weight else 1.0)
        return cls(tuple(names), tuple(weights))

    def label(self) -> str:
        if len(self.names) == 1:
            return self.names[0]
        return "+".join(f"{n}({w:g})" for n, w in zip(self.names, self.weights, strict=True))


def pool(first: str) -> tuple[str, ...]:
    """POOL led by the configured voice."""
    return (first, *(n for n in POOL if n != first))


def catalogue(first: str) -> list[VoiceSpec]:
    """Every voice to hand out, stock voices first, then blends."""
    names = pool(first)
    specs = [VoiceSpec((n,)) for n in names]
    # Same gender (the second letter, f or m), and English, which LANG phonemizes.
    pairs = [
        (a, b)
        for a, b in itertools.combinations(names, 2)
        if a[1] == b[1] and a[0] in LANG and b[0] in LANG
    ]
    for weights in BLEND_WEIGHTS:
        specs += [VoiceSpec((a, b), weights) for a, b in pairs]
    return specs


Table = dict[str, tuple[int, float]]  # key -> (catalogue index, last heard)


class VoiceBook:
    def __init__(
        self,
        path: Path,
        first: str = POOL[0],
        clock: Callable[[], float] = time.time,
        active_seconds: float = ACTIVE_SECONDS,
        home_seconds: float = HOME_SECONDS,
    ):
        """`clock` is wall time, since holds and homes outlive the daemon in `path`."""
        self._path = path
        self._specs = catalogue(first)
        self._index = {spec.label(): i for i, spec in enumerate(self._specs)}
        self._clock = clock
        self._active_seconds = active_seconds
        self._home_seconds = home_seconds
        self._home, self._held = self._load()  # by source, by session

    def default(self) -> VoiceSpec:
        return self._specs[0]

    def assign(self, session: str, source: str) -> VoiceSpec:
        """The voice for `session`, which works in repo `source`."""
        if not session:
            return self.default()
        now = self._clock()
        self._expire(now)
        if session in self._held:
            index = self._held[session][0]
        else:
            taken = {i for i, _ in self._held.values()}
            home = self._home.get(source)
            if home is not None and home[0] not in taken:
                index = home[0]
            else:
                index = self._first_free(taken, now)
                if source and home is None:
                    self._home[source] = (index, now)
        self._held[session] = (index, now)
        if source in self._home:
            self._home[source] = (self._home[source][0], now)
        self._save()
        return self._specs[index]

    def touch(self, session: str) -> None:
        """`session` sent a prompt, so it is still working: keep its voice held."""
        now = self._clock()
        self._expire(now)
        if session in self._held:
            self._held[session] = (self._held[session][0], now)
            self._save()

    def _expire(self, now: float) -> None:
        self._held = {
            s: (i, seen)
            for s, (i, seen) in self._held.items()
            if now - seen <= self._active_seconds
        }

    def _first_free(self, taken: set[int], now: float) -> int:
        # Prefer a voice no recently heard repo calls home, then any nobody active holds.
        homes = {i for i, seen in self._home.values() if now - seen <= self._home_seconds}
        for avoid in (taken | homes, taken):
            for i in range(len(self._specs)):
                if i not in avoid:
                    return i
        return len(self._held) % len(self._specs)  # every voice in use: repeat

    def _load(self) -> tuple[Table, Table]:
        try:
            raw = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return {}, {}
        if not isinstance(raw, dict):
            return {}, {}
        return self._entries(raw.get("homes")), self._entries(raw.get("sessions"))

    def _entries(self, raw: object) -> Table:
        """Stored by label, so a reordered pool keeps each voice; unknown labels drop."""
        out: Table = {}
        for key, entry in raw.items() if isinstance(raw, dict) else ():
            if not isinstance(entry, dict):
                continue
            label, seen = entry.get("voice"), entry.get("seen")
            if isinstance(label, str) and label in self._index and isinstance(seen, int | float):
                out[str(key)] = (self._index[label], float(seen))
        return out

    def _save(self) -> None:
        def entries(table: Table) -> dict[str, dict]:
            return {
                key: {"voice": self._specs[i].label(), "seen": seen}
                for key, (i, seen) in table.items()
            }

        data = {"homes": entries(self._home), "sessions": entries(self._held)}
        with contextlib.suppress(OSError):
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n")
            tmp.replace(self._path)
