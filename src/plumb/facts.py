"""The fact library: what can be supported, and with what evidence.

Every fact is computed deterministically from the possession engine and its evidence. Each one
carries three things the pitch is about:

* the **value**,
* the **coverage** it rests on — how much of the window the tracking actually supports,
* the **confidence interval**, which here is not a statistical nicety but a worst case: the value
  if *every* frame in which the ball was not observed had belonged to the other side.

That interval is the point of the project. A possession share computed over a feed that loses the
ball on 41 % of its frames is not a number with an error bar; it is a number with a hole in it,
and the hole can be measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple

import numpy as np

from mtah.config import ABSTAIN, AWAY, DEAD, HOME

from .analysis import Analysis

TEAM_NAMES = ("Barcelona", "Athletic Club")


@dataclass
class Fact:
    """A supported claim, with the ground it stands on."""

    id: str
    title: str
    answer: str
    detail: List[Tuple[str, str]] = field(default_factory=list)
    coverage: str = ""
    confidence: str = ""
    evidence: str = ""
    coverage_short: str = ""

    def __post_init__(self):
        if not self.coverage_short:
            head = self.coverage.split(";")[0].split(",")[0].strip()
            self.coverage_short = head[:34]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "answer": self.answer,
            "detail": [{"label": label, "value": value} for label, value in self.detail],
            "coverage": self.coverage,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


def _window_slice(analysis: Analysis, window: str) -> np.ndarray:
    """Boolean mask of the frames in a named window (ungraded frames included)."""
    start, end = analysis.window(window)
    mask = np.zeros(analysis.n_frames, dtype=bool)
    mask[start:end + 1] = True
    return mask


def _graded_frames(analysis: Analysis, window: str) -> np.ndarray:
    return _window_slice(analysis, window) & analysis.evidence.graded


def _alive_frames(analysis: Analysis, window: str) -> np.ndarray:
    graded = _graded_frames(analysis, window)
    return graded & (analysis.labels != DEAD)


def _unobserved_alive(analysis: Analysis, window: str) -> np.ndarray:
    """Alive frames in which the ball was not observed — the hole in the claim."""
    alive = _alive_frames(analysis, window)
    return alive & ~analysis.evidence.ball_present


def _share_interval(counts: np.ndarray, total: int, unobserved: int) -> Tuple[float, float]:
    """Worst-case interval for a proportion, given the frames we cannot see."""
    if total <= 0:
        return 0.0, 0.0
    low = counts[0] / total
    high = (counts[0] + unobserved) / total
    return low, high


def _fmt_pct(value: float) -> str:
    return "{:.1f} %".format(100.0 * value)


# --------------------------------------------------------------------------------------------------
# The facts
# --------------------------------------------------------------------------------------------------


def possession_share(analysis: Analysis, window: str = "all") -> Fact:
    """How much of the window each team had the ball."""
    alive = _alive_frames(analysis, window)
    total = int(alive.sum())
    home = int((analysis.labels[alive] == HOME).sum())
    away = int((analysis.labels[alive] == AWAY).sum())
    unobserved = int(_unobserved_alive(analysis, window).sum())

    if total == 0:
        return Fact("possession_share", "Possession share", "No live frames in that window.")

    low, high = _share_interval(np.array([home, away]), total, unobserved)
    share = home / total
    graded = int(_graded_frames(analysis, window).sum())
    coverage = total / graded if graded else 0.0

    start, end = analysis.window(window)
    return Fact(
        id="possession_share",
        title="Possession share ({})".format(window),
        answer="{} held the ball for {} of the live frames.".format(
            TEAM_NAMES[0], _fmt_pct(share)
        ),
        detail=[
            (TEAM_NAMES[0], _fmt_pct(share)),
            (TEAM_NAMES[1], _fmt_pct(1 - share)),
            ("live frames", "{:,} of {:,}".format(total, graded)),
        ],
        coverage="{} of the window's graded frames are live; the ball is observed on {} of them".format(
            _fmt_pct(coverage), _fmt_pct(1 - unobserved / total) if total else "—"
        ),
        confidence="{:.1f} % to {:.1f} % — the interval is what the unobserved frames allow".format(
            100 * low, 100 * high
        ),
        evidence="frames {:,}-{:,}".format(start, end),
    )


def possession_count(analysis: Analysis, window: str = "all") -> Fact:
    """How many possessions the window contains, and how long they run."""
    start, end = analysis.window(window)
    spells = [
        (a, b, label)
        for a, b, label in analysis.spells
        if label in (HOME, AWAY) and a <= end and b >= start
    ]
    durations = [(b - a) / 25.0 for a, b, _ in spells]
    unobserved = int(_unobserved_alive(analysis, window).sum())
    graded = int(_graded_frames(analysis, window).sum())

    if not durations:
        return Fact("possession_count", "Possessions ({})".format(window), "None.")

    return Fact(
        id="possession_count",
        title="Possessions ({})".format(window),
        answer="{} possessions, mean {:.1f} s, median {:.1f} s.".format(
            len(durations), float(np.mean(durations)), float(np.median(durations))
        ),
        detail=[
            ("possessions", str(len(durations))),
            ("mean length", "{:.1f} s".format(float(np.mean(durations)))),
            ("median length", "{:.1f} s".format(float(np.median(durations)))),
            ("longest", "{:.1f} s".format(float(np.max(durations)))),
        ],
        coverage="{} frames in the window have no ball observation".format(unobserved),
        confidence="spell boundaries rest on the frames where the ball is observed; "
                   "the count is bounded only by the smoothing rule, not by the data",
        evidence="frames {:,}-{:,}".format(start, end),
    )


def dead_ball(analysis: Analysis, window: str = "all") -> Fact:
    """How much of the window the ball was not in play."""
    graded = _graded_frames(analysis, window)
    dead = int((analysis.labels[graded] == DEAD).sum())
    total = int(graded.sum())
    blocks = [
        (a, b) for a, b, label in analysis.spells if label == DEAD and a <= analysis.window(window)[1] and b >= analysis.window(window)[0]
    ]
    longest = max(((b - a) / 25.0 for a, b in blocks), default=0.0)
    return Fact(
        id="dead_ball",
        title="Dead ball ({})".format(window),
        answer="{} of the window's graded frames are dead ball — {}.".format(
            "{:,}".format(dead), "{:.0f} seconds".format(dead / 25.0)
        ),
        detail=[
            ("dead frames", "{:,} of {:,}".format(dead, total)),
            ("share", _fmt_pct(dead / total) if total else "—"),
            ("dead spells", str(len(blocks))),
            ("longest dead spell", "{:.1f} s".format(longest)),
        ],
        coverage="detected from play state: the ball untracked while the players have stopped",
        confidence="a conservative test; dead periods where the ball stays visible are not "
                   "detected, so this is a lower bound",
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
    )


def longest_possession(analysis: Analysis, window: str = "all") -> Fact:
    """The longest spell of one team's possession in the window."""
    start, end = analysis.window(window)
    spells = [
        (a, b, label)
        for a, b, label in analysis.spells
        if label in (HOME, AWAY) and a <= end and b >= start
    ]
    if not spells:
        return Fact("longest_possession", "Longest possession", "None.")
    a, b, label = max(spells, key=lambda s: s[1] - s[0])
    duration = (b - a) / 25.0
    unobserved = int(_unobserved_alive(analysis, window).sum())
    return Fact(
        id="longest_possession",
        title="Longest possession ({})".format(window),
        answer="{} kept the ball for {:.1f} s, from frame {:,}.".format(
            TEAM_NAMES[label], duration, a
        ),
        detail=[
            ("team", TEAM_NAMES[label]),
            ("length", "{:.1f} s".format(duration)),
            ("from frame", "{:,}".format(a)),
            ("to frame", "{:,}".format(b)),
        ],
        coverage="{} frames in the window have no ball observation".format(unobserved),
        confidence="the boundaries are where the tracker last saw the ball with one team",
        evidence="frames {:,}-{:,}".format(a, b),
    )


def ball_visibility(analysis: Analysis, window: str = "all") -> Fact:
    """The coverage of the tracking itself — the central fact."""
    graded = _graded_frames(analysis, window)
    total = int(graded.sum())
    seen = int((analysis.evidence.ball_present & graded).sum())
    share = seen / total if total else 0.0
    gaps = _longest_gaps(analysis, window)
    return Fact(
        id="ball_visibility",
        title="Tracking coverage ({})".format(window),
        answer="the ball is observed on {} of the window's graded frames.".format(_fmt_pct(share)),
        detail=[
            ("graded frames", "{:,}".format(total)),
            ("ball observed", "{:,} ({})".format(seen, _fmt_pct(share))),
            ("ball not observed", "{:,} ({})".format(total - seen, _fmt_pct(1 - share))),
            ("longest gap", "{:.1f} s".format(gaps[1]) if gaps else "—"),
        ],
        coverage="the measure of the feed itself",
        confidence="exact — this is a count, not an estimate",
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
    )


def _longest_gaps(analysis: Analysis, window: str) -> Tuple[int, float]:
    """The longest stretch of graded frames with no ball observation."""
    graded = _graded_frames(analysis, window)
    missing = graded & ~analysis.evidence.ball_present
    best_length = 0
    best_start = 0
    run = 0
    for index in range(analysis.n_frames):
        if missing[index]:
            run += 1
            if run > best_length:
                best_length = run
                best_start = index - run + 1
        else:
            run = 0
    return best_start, best_length / 25.0


def possession_changes(analysis: Analysis, window: str = "all") -> Fact:
    """How often possession changed hands in the window."""
    start, end = analysis.window(window)
    changes = 0
    previous = None
    for index in range(start, min(end + 1, analysis.n_frames)):
        label = int(analysis.labels[index])
        if label not in (HOME, AWAY):
            previous = None
            continue
        if previous is not None and label != previous:
            changes += 1
        previous = label
    graded = int(_graded_frames(analysis, window).sum())
    return Fact(
        id="possession_changes",
        title="Changes of possession ({})".format(window),
        answer="{} changes of possession.".format(changes),
        detail=[
            ("changes", str(changes)),
            ("per minute", "{:.2f}".format(changes / max(1e-9, (end - start + 1) / 1500.0))),
            ("graded frames", "{:,}".format(graded)),
        ],
        coverage="counted only where the ball is alive and a team is holding it",
        confidence="a change can only be seen where the tracker saw the ball change hands",
        evidence="frames {:,}-{:,}".format(start, end),
    )


def ball_thirds(analysis: Analysis, window: str = "all") -> Fact:
    """Where the ball was, in thirds of the pitch, while the game was live."""
    alive = _alive_frames(analysis, window)
    if not alive.any():
        return Fact("ball_thirds", "Ball position", "No live frames.")
    length = analysis.evidence.n_frames and 105.3
    x = analysis.ball_xy[:, 0]
    third = np.where(x < length / 3, 0, np.where(x < 2 * length / 3, 1, 2))
    names = ("defensive third", "middle third", "attacking third")
    total = int(alive.sum())
    detail = []
    for index in range(3):
        count = int(((third == index) & alive).sum())
        detail.append((names[index], "{} ({})".format(count, _fmt_pct(count / total))))
    return Fact(
        id="ball_thirds",
        title="Where the ball was ({})".format(window),
        answer="the ball was in the middle third for {} of the live frames.".format(
            _fmt_pct(int(((third == 1) & alive).sum()) / total)
        ),
        detail=detail,
        coverage="frames in which the ball is observed and the game is live",
        confidence="the position is the tracker's, to the accuracy of the tracking error",
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
    )


FACT_LIBRARY: Dict[str, Callable[..., Fact]] = {
    "possession_share": possession_share,
    "possession_count": possession_count,
    "dead_ball": dead_ball,
    "longest_possession": longest_possession,
    "ball_visibility": ball_visibility,
    "possession_changes": possession_changes,
    "ball_thirds": ball_thirds,
}
