"""A distinct voice for each Claude Code terminal, kept per repo across restarts.

A repo keeps the first voice it was given that no other repo calls home, unless another
terminal is using it; then, like a second terminal in the same repo, it borrows the next
voice nobody holds. A terminal holds its voice while its Claude Code process runs, across
`/clear` and resume. Every single voice is handed out before any blend, since each is a
character on klepsydra's wall; past them come same-gender blends, so voices only repeat once
every blend is taken too.
Homes and holds are saved, so a daemon restart changes nobody's voice.
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

from keryx.procs import is_alive

# Kokoro v1.0's English voices graded C or better in its VOICES.md (research 2026-10). The
# first ten have character portraits on klepsydra's fleet wall, so the first ten terminals
# get them; those alternate accent and gender where the set allows, best grades first.
POOL = (
    "af_heart",  # A
    "am_michael",  # C+
    "bf_emma",  # B-
    "am_puck",  # C+
    "af_bella",  # A-
    "bf_isabella",  # C
    "af_kore",  # C+
    "af_sarah",  # C+
    "af_nova",  # C
    "af_aoede",  # C+, Dokimasia: last of the ten on purpose
    "bm_george",  # C
    "am_fenrir",  # C+
    "bm_fable",  # C
    "af_alloy",  # C
)

# Voices handed out only after every pool voice is held (even a pool voice an idle repo calls
# home is borrowed first), and never as a blend or the lead. Kokoro tags
# af_nicole with a headphone/ASMR marker, but she is a character on klepsydra's wall, and every
# character comes before any blend.
SPECIALTY = ("af_nicole",)

# Every voice `keryx voice` offers and may set: the rotation pool plus the specialty voices. The
# config `voice` may still name any Kokoro voice; that is the power-user escape hatch.
SELECTABLE = (*POOL, *SPECIALTY)

LANG = {"a": "en-us", "b": "en-gb"}

# Blends of voices far apart (another gender) come out muddy, so only same-gender pairs.
BLEND_WEIGHTS = ((0.5, 0.5), (0.7, 0.3), (0.3, 0.7))

# A holder without a process to watch (no Claude Code ancestor) keeps its voice this long
# after its last prompt or reply.
ACTIVE_SECONDS = 4 * 3600
# A repo silent this long stops reserving its home voice; after FORGET it is dropped.
HOME_SECONDS = 14 * 24 * 3600
FORGET_SECONDS = 90 * 24 * 3600
# Refreshed timestamps alone are saved at most this often; new holds and homes at once.
SAVE_SECONDS = 60


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
        """Phonemes for the voice that weighs most (the first, on a tie), so a mostly British
        blend sounds British."""
        heaviest = self.names[max(range(len(self.weights)), key=self.weights.__getitem__)]
        return LANG.get(heaviest[0], "en-us")

    def spoken(self) -> str:
        """The voice's name to say aloud: `heart`, or `heart and emma`."""
        return " and ".join(name.partition("_")[2] or name for name in self.names)

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


def holder(terminal: str, session: str) -> str:
    """Who holds a voice: the terminal, or the session outside one."""
    return terminal or session


def pool(first: str) -> tuple[str, ...]:
    """The rotation POOL led by the configured voice. A SPECIALTY voice never leads, so it is
    handed out only after the pool; any other voice leads (a non-curated or non-English
    Kokoro voice is still honored as the config `voice`, per 'the first voice handed out')."""
    lead = POOL[0] if first in SPECIALTY else first
    return (lead, *(n for n in POOL if n != lead))


def catalogue(first: str) -> list[VoiceSpec]:
    """Every voice to hand out: the pool, then the specialty voices, then blends of the pool."""
    names = pool(first)
    specs = [VoiceSpec((n,)) for n in (*names, *SPECIALTY)]
    # Same gender (the second letter, f or m), and English, which LANG phonemizes.
    # Each pair in name order, so its labels do not change with the configured voice.
    pairs = [
        tuple(sorted((a, b)))
        for a, b in itertools.combinations(names, 2)
        if a[1] == b[1] and a[0] in LANG and b[0] in LANG
    ]
    for weights in BLEND_WEIGHTS:
        specs += [VoiceSpec((a, b), weights) for a, b in pairs]
    return specs


def stock(first: str) -> list[VoiceSpec]:
    """The single-voice choices `keryx voice` offers: the rotation pool then the specialty voices,
    no blends. `first` leads when it is a selectable voice, else the default lead does, so the
    list never offers a voice the daemon would refuse while still showing the user's current one."""
    lead = first if first in SELECTABLE else POOL[0]
    return [VoiceSpec((n,)) for n in (lead, *(n for n in SELECTABLE if n != lead))]


def resolve(choice: str, specs: list[VoiceSpec]) -> str | None:
    """A voice label from a 1-based number or a name (`bella`, `af_bella`, or the full label),
    matched against `specs`; None when nothing matches."""
    choice = choice.strip()
    if choice.isdigit():
        i = int(choice) - 1
        return specs[i].label() if 0 <= i < len(specs) else None
    low = choice.lower()
    for spec in specs:
        if low in {spec.label().lower(), spec.spoken().lower(), spec.names[0].lower()}:
            return spec.label()
    return None


Table = dict[str, tuple[int, float]]  # key -> (catalogue index, last heard)


class VoiceBook:
    def __init__(
        self,
        path: Path,
        first: str = POOL[0],
        clock: Callable[[], float] = time.time,
        active_seconds: float = ACTIVE_SECONDS,
        home_seconds: float = HOME_SECONDS,
        alive: Callable[[str], bool | None] = is_alive,
        available: Callable[[VoiceSpec], bool] = lambda _spec: True,
    ):
        """`clock` is wall time, since holds and homes outlive the daemon in `path`.

        `alive(holder)` says whether a terminal's process still runs, or None for a holder
        that is not a terminal (a bare session id), which then lapses after `active_seconds`.

        `available(spec)` says whether the synthesizer actually has a voice; a voice (or blend)
        the current Kokoro lacks is dropped, so rotation never hands out one it cannot speak.
        """
        self._alive = alive
        self._path = path
        # Rotation must never be empty, even if `available` rejects everything, so it always has
        # a voice to hand out and `_first_free` never divides by zero.
        self._specs = [spec for spec in catalogue(first) if available(spec)] or [
            VoiceSpec((POOL[0],))
        ]
        self._singles = sum(len(spec.names) == 1 for spec in self._specs)  # they lead the list
        # Specialty singles: handed out after the pool, and left for a pool voice once one frees.
        self._specialty = {i for i in range(self._singles) if self._specs[i].names[0] in SPECIALTY}
        self._index = {spec.label(): i for i, spec in enumerate(self._specs)}
        self._clock = clock
        self._active_seconds = active_seconds
        self._home_seconds = home_seconds
        self._home, self._held = self._load()  # by source, by holder
        self._saved = float("-inf")

    def default(self) -> VoiceSpec:
        return self._specs[0]

    def assign(self, holder: str, source: str) -> VoiceSpec:
        """The voice for `holder` (a terminal, else a session), working in repo `source`.

        Without a holder (`keryx say`, scripts): the first voice nobody holds, so a notice
        is never mistaken for a terminal's line.
        """
        now = self._clock()
        self._expire(now)
        taken = {i for h, (i, _) in self._held.items() if h != holder}
        if not holder:
            return self._specs[next((i for i in range(len(self._specs)) if i not in taken), 0)]
        changed = holder not in self._held
        home = self._home.get(source)
        # The repo's own voice when it is a free single voice, else the first free single voice.
        home_free = home is not None and home[0] not in taken
        single = (
            home[0]
            if home_free and home[0] < self._singles
            else self._first_free(taken, now, self._singles)
        )
        if not changed:
            index = self._held[holder][0]
            # A terminal on a blend (only rotation hands one out) moves to a single voice.
            if index >= self._singles and single is not None:
                index, changed = single, True
        elif single is not None:
            index = single
        elif home_free:
            index = home[0]  # a blend home, with no single voice free
        else:
            index = self._first_free(taken, now, len(self._specs))
            if index is None:
                index = len(self._held) % len(self._specs)  # every voice in use: repeat
        # A repo's first voice becomes its home, as does a single voice for a repo homed in a blend,
        # unless another repo heard lately calls it home: a borrowed voice stays borrowed.
        homed_elsewhere = any(
            i == index and s != source and now - seen <= self._home_seconds
            for s, (i, seen) in self._home.items()
        )
        if (
            source
            and changed
            and not homed_elsewhere
            and (home is None or (home[0] >= self._singles > index))
        ):
            self._home[source] = (index, now)
        self._held[holder] = (index, now)
        # A repo counts as heard only in its own voice, not in one a terminal brought along.
        if source in self._home and self._home[source][0] == index:
            self._home[source] = (index, now)
        self._save(now, force=changed)
        return self._specs[index]

    def pin(self, holder: str, label: str) -> bool:
        """Hold `holder` on the voice `label`, overriding what it would be handed.

        For `keryx voice`: the terminal the user picked a voice in keeps that voice until they
        pick again, while every other terminal keeps its own. Returns False when the label is
        not a voice in the catalogue, or there is no terminal to pin (a bare shell).
        """
        index = self._index.get(label)
        if index is None or not holder:
            return False
        now = self._clock()
        self._expire(now)
        self._held[holder] = (index, now)
        self._save(now, force=True)
        return True

    def _expire(self, now: float) -> None:
        # A clock that jumped back (WSL after the host sleeps) must not make holds eternal.
        held = {s: (i, min(seen, now)) for s, (i, seen) in self._held.items()}
        self._held = {}
        for holder, (i, seen) in held.items():
            running = self._alive(holder)
            if running or (running is None and now - seen <= self._active_seconds):
                self._held[holder] = (i, seen)
        self._home = {
            s: (i, min(seen, now))
            for s, (i, seen) in self._home.items()
            if now - min(seen, now) <= FORGET_SECONDS
        }

    def _first_free(self, taken: set[int], now: float, below: int) -> int | None:
        """The first voice under index `below` nobody holds, or None. Pool voices come first, then
        specialty voices, then blends; within each, a voice no recent repo calls home comes before
        one that does."""
        homes = {i for i, seen in self._home.values() if now - seen <= self._home_seconds}
        pooled = [i for i in range(self._singles) if i not in self._specialty]
        tiers = (pooled, sorted(self._specialty), range(self._singles, below))
        for tier in tiers:
            for avoid in (taken | homes, taken):
                for i in tier:
                    if i not in avoid:
                        return i
        return None

    def _load(self) -> tuple[Table, Table]:
        try:
            raw = json.loads(self._path.read_text())
        except (OSError, ValueError):
            return {}, {}
        if not isinstance(raw, dict):
            return {}, {}
        return self._entries(raw.get("homes")), self._entries(raw.get("holders"))

    def _entries(self, raw: object) -> Table:
        """Stored by label, so a reordered pool keeps each voice; unknown labels drop."""
        out: Table = {}
        for key, entry in raw.items() if isinstance(raw, dict) else ():
            if not isinstance(entry, dict):
                continue
            label, seen = entry.get("voice"), entry.get("seen")
            if (
                isinstance(label, str)
                and label in self._index
                and isinstance(seen, int | float)
                and math.isfinite(seen)
            ):
                out[str(key)] = (self._index[label], float(seen))
        return out

    def _save(self, now: float, force: bool) -> None:
        if not force and 0 <= now - self._saved < SAVE_SECONDS:  # < 0: the clock jumped back
            return
        self._saved = now

        def entries(table: Table) -> dict[str, dict]:
            return {
                key: {"voice": self._specs[i].label(), "seen": seen}
                for key, (i, seen) in table.items()
            }

        data = {"homes": entries(self._home), "holders": entries(self._held)}
        with contextlib.suppress(OSError):
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2) + "\n")
            tmp.replace(self._path)
