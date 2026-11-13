"""The fact library: what can be supported, and with what evidence.

Every fact is computed deterministically from the possession engine and its evidence. Each one
carries four things the pitch is about:

* the **value**,
* the **scope** — what the claim is about, in the organisers' own vocabulary where they have
  one ("a BUILD UP phase", "the final third", "the first half"),
* the **coverage** it rests on — how much of *that scope* the tracking actually supports,
* the **confidence interval**, which here is not a statistical nicety but a worst case: the value
  if *every* frame in which the ball was not observed had belonged to the other side.

That interval is the point of the project. A possession share computed over a feed that loses the
ball on 41 % of its frames is not a number with an error bar; it is a number with a hole in it,
and the hole can be measured — **for the scope the claim is about**, not for the match.

The tactical facts are keyed to the organisers' own Smart Tagging codes, because those codes are
the vocabulary their Innovation Challenge brief is written in, and because each code comes with
an annotation we can be checked against. That check uses no possession ground truth at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from mtah.config import ABSTAIN, AWAY, DEAD, HOME

from . import phases as phase_tools
from .analysis import Analysis
from .tactics import TACTICS, attacking_sides, tactics_scope

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
    scope: str = ""
    coverage_short: str = ""
    coverage_pct: Optional[float] = None  # the share of the claim's own scope with the ball seen

    def __post_init__(self):
        if not self.coverage_short:
            if self.coverage_pct is not None:
                self.coverage_short = "{:.1f} % of the scope observed".format(
                    100.0 * self.coverage_pct)
            else:
                head = self.coverage.split(";")[0].split(",")[0].strip()
                self.coverage_short = head[:34]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "answer": self.answer,
            "scope": self.scope,
            "detail": [{"label": label, "value": value} for label, value in self.detail],
            "coverage": self.coverage,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "coverage_pct": self.coverage_pct,
        }


# --------------------------------------------------------------------------------------------------
# Frame selection
# --------------------------------------------------------------------------------------------------


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


def _scoped_frames(analysis: Analysis, window: str, zone: Optional[str] = None,
                   phase: Optional[str] = None) -> np.ndarray:
    """The frames a claim is about: the window, then the zone, then the phase."""
    from .tactics import tactics_scope

    frames = _window_slice(analysis, window)
    if zone and zone != "all":
        frames = frames & tactics_scope(analysis, zone)
    if phase:
        frames = frames & phase_frames(analysis, phase)
    return frames


def phase_frames(analysis: Analysis, code: str) -> np.ndarray:
    """The frames of the Smart Tagging instances with a given code."""
    frames = np.zeros(analysis.n_frames, dtype=bool)
    for instance in phase_tools.by_code(analysis.phases, code):
        lo = max(0, instance.start)
        hi = min(analysis.n_frames - 1, instance.end)
        if hi >= lo:
            frames[lo:hi + 1] = True
    return frames


def _scope_text(window: str, zone: Optional[str] = None, code: Optional[str] = None) -> str:
    """A human phrase for what a claim is about."""
    parts = []
    if code:
        parts.append("the {} phases".format(code.lower()))
    if zone and zone != "all" and not code:
        parts.append("in the {}".format(zone.replace("-", " ")))
    if window and window != "all":
        parts.append("in the {}".format(window.replace("-", " ")))
    if not parts:
        return "the whole match"
    return " ".join(parts)


def _coverage_sentence(analysis: Analysis, frames: np.ndarray) -> str:
    """The coverage of a claim, over the frames it depends on."""
    scope = analysis.coverage().scope(frames)
    if scope["frames"] == 0:
        return "nothing to measure"
    return (
        "{:.1f} % of the scoped frames have the ball observed; the tracking supports {:.0%} "
        "of them".format(
            100.0 * scope["ball_visibility"], scope["support"]
        )
    )


def _coverage_pct(analysis: Analysis, frames: np.ndarray) -> float:
    """The share of a claim's own frames in which the ball was observed."""
    frames = np.asarray(frames, dtype=bool)
    if not frames.any():
        return 0.0
    return float(analysis.evidence.ball_present[frames].mean())


def _coverage_pct_range(analysis: Analysis, start: int, stop: int) -> float:
    """The same, for a half-open range of frames."""
    stop = min(stop, analysis.n_frames)
    if stop <= start:
        return 0.0
    window = analysis.evidence.ball_present[start:stop]
    return float(window.mean())


def _sensitivity_sentence(analysis: Analysis, frames: np.ndarray, sigma: float = 0.5) -> str:
    """How much of the scope was decided by a thin margin."""
    share = analysis.coverage().sensitivity(frames, sigma)
    return (
        "{:.1f} % of the scoped frames were decided by less than {} m; a tracking error of that "
        "size would move them".format(100.0 * share, sigma)
    )


# --------------------------------------------------------------------------------------------------
# The possession facts
# --------------------------------------------------------------------------------------------------


def possession_share(analysis: Analysis, window: str = "all", zone: str = None,
                    phase: str = None) -> Fact:
    """How much of the window each team had the ball."""
    alive = _alive_frames(analysis, window) & _scoped_frames(analysis, window, zone, phase)
    total = int(alive.sum())
    home = int((analysis.labels[alive] == HOME).sum())
    away = int((analysis.labels[alive] == AWAY).sum())
    unobserved = int((alive & ~analysis.evidence.ball_present).sum())

    if total == 0:
        return Fact(
            "possession_share",
            "Possession share",
            "No live frames in that scope.",
            scope=_scope_text(window, zone),
        )

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
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, alive),
    )


def possession_count(analysis: Analysis, window: str = "all", zone: str = None,
                    phase: str = None) -> Fact:
    """How many possessions the window contains, and how long they run."""
    start, end = analysis.window(window)
    zone_mask = tactics_scope(analysis, zone) if zone and zone != "all" else None
    spells = []
    for a, b, label in analysis.spells:
        if label not in (HOME, AWAY) or a > end or b < start:
            continue
        if zone_mask is not None and not zone_mask[a:min(b, analysis.n_frames)].any():
            continue
        spells.append((a, b, label))
    durations = [(b - a) / 25.0 for a, b, _ in spells]
    unobserved = int(_unobserved_alive(analysis, window).sum())
    graded = int(_graded_frames(analysis, window).sum())

    if not durations:
        return Fact(
            "possession_count",
            "Possessions ({})".format(window),
            "None.",
            scope=_scope_text(window, zone, phase),
        )

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
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, _graded_frames(analysis, window)),
    )


def dead_ball(analysis: Analysis, window: str = "all", zone: str = None,
               phase: str = None) -> Fact:
    """How much of the window the ball was not in play."""
    graded = _graded_frames(analysis, window)
    dead = int((analysis.labels[graded] == DEAD).sum())
    total = int(graded.sum())
    start, end = analysis.window(window)
    blocks = [
        (a, b) for a, b, label in analysis.spells if label == DEAD and a <= end and b >= start
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
        evidence="frames {:,}-{:,}".format(start, end),
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, _graded_frames(analysis, window)),
    )


def longest_possession(analysis: Analysis, window: str = "all", zone: str = None,
                     phase: str = None) -> Fact:
    """The longest spell of one team's possession in the window."""
    start, end = analysis.window(window)
    spells = [
        (a, b, label)
        for a, b, label in analysis.spells
        if label in (HOME, AWAY) and a <= end and b >= start
    ]
    if not spells:
        return Fact(
            "longest_possession",
            "Longest possession",
            "None.",
            scope=_scope_text(window, zone, phase),
        )
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
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct_range(analysis, a, b),
    )


def ball_visibility(analysis: Analysis, window: str = "all", zone: str = None,
                  phase: str = None) -> Fact:
    """The coverage of the tracking itself — the central fact."""
    graded = _graded_frames(analysis, window) & _scoped_frames(analysis, window, zone, phase)
    total = int(graded.sum())
    seen = int((analysis.evidence.ball_present & graded).sum())
    share = seen / total if total else 0.0
    gaps = _longest_gaps(graded, analysis.evidence.ball_present)
    scope = analysis.coverage().scope(graded)
    return Fact(
        id="ball_visibility",
        title="Tracking coverage ({})".format(
            _scope_text(window, zone, phase) if (zone or phase) else window),
        answer="the ball is observed on {} of the window's graded frames.".format(_fmt_pct(share)),
        detail=[
            ("graded frames", "{:,}".format(total)),
            ("ball observed", "{:,} ({})".format(seen, _fmt_pct(share))),
            ("ball not observed", "{:,} ({})".format(total - seen, _fmt_pct(1 - share))),
            ("longest gap", "{:.1f} s".format(gaps[1]) if gaps else "—"),
            ("support score", "{:.0%}".format(scope["support"])),
            ("duplicate players", "{:.1%} of the frames".format(scope["duplicate_share"])),
        ],
        coverage="the measure of the feed itself: {:.1f} % of the scoped frames have the ball "
                 "observed".format(100.0 * scope["ball_visibility"]),
        confidence="exact — this is a count, not an estimate",
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
        scope=_scope_text(window, zone, phase),
        coverage_pct=scope["ball_visibility"],
    )


def _longest_gaps(graded: np.ndarray, ball_present: np.ndarray) -> Tuple[int, float]:
    """The longest stretch of frames in the scope with no ball observation."""
    missing = graded & ~ball_present
    best_length = 0
    best_start = 0
    run = 0
    for index in range(graded.shape[0]):
        if missing[index]:
            run += 1
            if run > best_length:
                best_length = run
                best_start = index - run + 1
        else:
            run = 0
    return best_start, best_length / 25.0


def possession_changes(analysis: Analysis, window: str = "all", zone: str = None,
                     phase: str = None) -> Fact:
    """How often possession changed hands in the window."""
    start, end = analysis.window(window)
    zone_mask = tactics_scope(analysis, zone) if zone and zone != "all" else None
    changes = 0
    previous = None
    for index in range(start, min(end + 1, analysis.n_frames)):
        if zone_mask is not None and not zone_mask[index]:
            previous = None
            continue
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
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, _graded_frames(analysis, window)),
    )


def ball_thirds(analysis: Analysis, window: str = "all", zone: str = None,
                phase: str = None) -> Fact:
    """Where the ball was, in thirds of the pitch, while the game was live."""
    alive = _alive_frames(analysis, window) & _scoped_frames(analysis, window, zone, phase)
    if not alive.any():
        return Fact(
            "ball_thirds",
            "Ball position",
            "No live frames.",
            scope=_scope_text(window, zone),
        )
    length = 105.3
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
        scope=_scope_text(window, zone),
        coverage_pct=_coverage_pct(analysis, alive),
    )


# --------------------------------------------------------------------------------------------------
# The tactical facts
# --------------------------------------------------------------------------------------------------


def _agreement_line(analysis: Analysis, code: str) -> str:
    """How often our possession labels agree with the organisers' annotation of a code.

    This is the check that matters, and it is legal: the Smart Tagging is provided data, and no
    possession ground truth is involved anywhere.
    """
    result = phase_tools.agreement(analysis.phases, code, analysis.labels)
    if not result["instances"]:
        return ""
    return (
        "our labels agree with the organisers' own {} annotation on {:.1%} of {} frames".format(
            code.lower(), result["agreement"], int(result["frames"])
        )
    )


def _tactic_fact(analysis: Analysis, tactic, window: str, zone: str = None,
                 phase: str = None, code: str = None) -> Fact:
    """Turn a tactic computation into a fact with claim-scoped coverage.

    ``code`` is the Smart Tagging code the aspect corresponds to, and it is used only for the
    agreement line — the *scope* is what the question asked about, not the code.
    """
    frames = tactic.frames
    scope = analysis.coverage().scope(frames)
    agreement = _agreement_line(analysis, code) if code else ""

    confidence = tactic.confidence
    if agreement:
        confidence = "{}; {}".format(agreement, confidence)

    detail = list(tactic.detail)
    if scope["frames"]:
        detail.append(("scoped frames", "{:,}".format(scope["frames"])))

    return Fact(
        id=tactic.id,
        title=tactic.title,
        answer=tactic.answer,
        detail=detail,
        coverage=_coverage_sentence(analysis, frames),
        confidence=confidence,
        evidence="frames {:,}-{:,}".format(
            int(np.flatnonzero(frames)[0]) if frames.any() else 0,
            int(np.flatnonzero(frames)[-1]) if frames.any() else 0,
        ),
        scope=_scope_text(window, zone, phase),
        coverage_pct=scope["ball_visibility"],
    )


def build_up(analysis: Analysis, window: str = "all", zone: str = None,
          phase: str = None) -> Fact:
    """How the team in possession played the ball out."""
    mask = _scoped_frames(analysis, window, zone, phase)
    tactic = TACTICS["build_up"](analysis, mask, analysis.geometry())
    return _tactic_fact(analysis, tactic, window, zone, phase, code="BUILD UP")


def progression(analysis: Analysis, window: str = "all", zone: str = None,
             phase: str = None) -> Fact:
    """How far the ball travelled up the pitch while a team was in possession.

    Two numbers, because they answer different questions: **carried** is how far the ball was
    taken up the pitch in total (the sum of the forward steps), and **net** is how much further
    up the pitch the possession finished than it started.
    """
    mask = _scoped_frames(analysis, window, zone, phase)
    alive = mask & (analysis.labels != DEAD) & analysis.evidence.ball_present
    # The claim rests on the possession frames; the coverage is then the share of them the
    # tracker could carry.
    resting = mask & (analysis.labels != DEAD)
    home_right = attacking_sides(analysis)
    length = analysis.pitch_length_m
    own_right = np.where(analysis.labels == HOME, home_right, ~home_right)
    progress = np.where(own_right, analysis.ball_xy[:, 0], length - analysis.ball_xy[:, 0])

    carried = []
    net = []
    possessions = [
        (a, b, label) for a, b, label in analysis.spells
        if label in (HOME, AWAY) and mask[a:min(b, analysis.n_frames)].any()
    ]
    for a, b, label in possessions:
        stop = min(b, analysis.n_frames)
        values = progress[a:stop][alive[a:stop]]
        if values.size < 2:
            continue
        steps = np.diff(values)
        carried.append(float(np.clip(steps, 0, None).sum()))
        net.append(float(values[-1] - values[0]))

    carried_mean = float(np.mean(carried)) if carried else 0.0
    net_mean = float(np.mean(net)) if net else 0.0
    detail = [
        ("possessions", str(len(possessions))),
        ("carried up the pitch", "{:.1f} m per possession".format(carried_mean)),
        ("net gain", "{:+.1f} m per possession".format(net_mean)),
    ]
    agreement = _agreement_line(analysis, "PROGRESSION")
    detail.append(("annotation", "{} PROGRESSION phases".format(
        len(phase_tools.by_code(analysis.phases, "PROGRESSION")))))
    return Fact(
        id="progression",
        title="Progression",
        answer="a possession carried the ball {:.1f} m up the pitch, for a net gain of "
               "{:+.1f} m.".format(carried_mean, net_mean),
        detail=detail,
        coverage=_coverage_sentence(analysis, resting),
        confidence="{}; the distance is integrated from the tracker's own ball positions, so it "
                   "carries the tracker's error".format(agreement),
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, resting),
    )


def creating_chances(analysis: Analysis, window: str = "all", zone: str = None,
                  phase: str = None) -> Fact:
    """How often a possession reached the final third and the box."""
    mask = _scoped_frames(analysis, window, zone, phase)
    tactic = TACTICS["chance_creation"](analysis, mask, analysis.geometry())
    return _tactic_fact(analysis, tactic, window, code="CREATING CHANCES")


def attacking_transition(analysis: Analysis, window: str = "all", zone: str = None,
                      phase: str = None) -> Fact:
    """What the winning team does in the ten seconds after it wins the ball.

    The mirror of :func:`defensive_transition`: where the new owner takes the ball, and how
    quickly.
    """
    mask = _scoped_frames(analysis, window, zone, phase)
    alive = mask & (analysis.labels != DEAD) & analysis.evidence.ball_present
    resting = mask & (analysis.labels != DEAD)
    home_right = attacking_sides(analysis)
    length = analysis.pitch_length_m
    own_right = np.where(analysis.labels == HOME, home_right, ~home_right)
    progress = np.where(own_right, analysis.ball_xy[:, 0], length - analysis.ball_xy[:, 0])

    possessions = [
        (a, b, label) for a, b, label in analysis.spells
        if label in (HOME, AWAY) and mask[a:min(b, analysis.n_frames)].any()
    ]
    gained = []
    carried = []
    for index in range(1, len(possessions)):
        previous_a, previous_b, previous_label = possessions[index - 1]
        a, b, label = possessions[index]
        if label == previous_label:
            continue
        stop = min(b, analysis.n_frames)
        window_progress = progress[a:stop][alive[a:stop]]
        if window_progress.size < 2:
            continue
        gained.append(float(window_progress[-1] - window_progress[0]))
        carried.append(float(np.clip(np.diff(window_progress), 0, None).sum()))

    gain_mean = float(np.mean(gained)) if gained else 0.0
    carried_mean = float(np.mean(carried)) if carried else 0.0
    detail = [
        ("changes of hands", str(len(gained))),
        ("net gain", "{:+.1f} m in the first stretch of possession".format(gain_mean)),
        ("carried forward", "{:.1f} m".format(carried_mean)),
    ]
    agreement = _agreement_line(analysis, "ATTACKING TRANSITION")
    return Fact(
        id="attacking_transition",
        title="Attacking transition",
        answer="after winning the ball, a team carried it {:.1f} m forward, for a net gain of "
               "{:+.1f} m.".format(carried_mean, gain_mean),
        detail=detail,
        coverage=_coverage_sentence(analysis, resting),
        confidence="{}; a transition is measured from the first observed frame of the new "
                   "possession, so a possession the tracker loses at the start is measured over "
                   "the part that was seen".format(agreement),
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, resting),
    )


def defensive_transition(analysis: Analysis, window: str = "all", zone: str = None,
                      phase: str = None) -> Fact:
    """How the defending team reacts to losing the ball.

    The counter-press: how often the team that lost it wins it straight back.
    """
    mask = _scoped_frames(analysis, window, zone, phase)
    tactic = TACTICS["transitions"](analysis, mask, analysis.geometry())
    return _tactic_fact(analysis, tactic, window, code="DEFENSIVE TRANSITION")


def defending_shape(analysis: Analysis, window: str = "all", zone: str = None,
                 phase: str = None) -> Fact:
    """The shape of the team that does not have the ball."""
    mask = _scoped_frames(analysis, window, zone, phase)
    tactic = TACTICS["defending"](analysis, mask, analysis.geometry())
    return _tactic_fact(analysis, tactic, window, code="DEFENDING IN MIDDLE THIRD")


def pressing(analysis: Analysis, window: str = "all", zone: str = None,
          phase: str = None) -> Fact:
    """How the team without the ball presses, and whether the press wins it."""
    mask = _scoped_frames(analysis, window, zone, phase)
    tactic = TACTICS["pressing"](analysis, mask, analysis.geometry())
    return _tactic_fact(analysis, tactic, window, zone, phase, code="DEFENSIVE TRANSITION")


def restarts(analysis: Analysis, window: str = "all", zone: str = None,
          phase: str = None) -> Fact:
    """Set pieces: who takes them, and who keeps the ball afterwards."""
    mask = _scoped_frames(analysis, window, zone, phase)
    tactic = TACTICS["restarts"](analysis, mask, analysis.geometry())
    return _tactic_fact(analysis, tactic, window, zone, phase, code="SET PIECES")


def long_ball(analysis: Analysis, window: str = "all", zone: str = None,
           phase: str = None) -> Fact:
    """How often the ball was played long, and what came of it."""
    mask = _scoped_frames(analysis, window, zone, phase)
    alive = mask & (analysis.labels != DEAD) & analysis.evidence.ball_present
    resting = mask & (analysis.labels != DEAD)
    if not alive.any():
        return Fact("long_ball", "Long balls", "No live frames.", scope=_scope_text(window))

    speed = np.abs(np.gradient(analysis.ball_xy[:, 0])) * 25.0
    speed[~alive] = np.nan
    long_balls = alive & (speed > 15.0)  # 15 m/s is a long ball; 54 km/h

    detail = [
        ("live frames", "{:,}".format(int(alive.sum()))),
        ("frames with a long ball", "{:,} ({:.1%})".format(
            int(long_balls.sum()), float(np.nanmean(long_balls[alive])))),
        ("peak ball speed", "{:.1f} m/s".format(
            float(np.nanmax(speed[alive])) if np.isfinite(speed[alive]).any() else 0.0)),
    ]
    agreement = _agreement_line(analysis, "LONG BALL")
    return Fact(
        id="long_ball",
        title="Long balls",
        answer="the ball was travelling faster than 15 m/s on {} of the live frames.".format(
            "{:,}".format(int(long_balls.sum()))),
        detail=detail,
        coverage=_coverage_sentence(analysis, resting),
        confidence="{}; the speed is differentiated from the tracker's own positions, so it "
                   "carries the tracker's error".format(agreement),
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
        scope=_scope_text(window, zone, phase),
        coverage_pct=_coverage_pct(analysis, resting),
    )


def box_presence(analysis: Analysis, window: str = "all", zone: str = None,
              phase: str = None) -> Fact:
    """How many players each team had in its own penalty area — against the organisers' own count.

    This is the sharpest check in the system, and it is the one that needs no possession labels
    at all: it is a count of players inside a rectangle, checked against a number the
    organisers wrote down. The Smart Tagging states "Max Players in the box" for 91 of its
    instances; we count the same thing from the tracking.

    Reading the annotation correctly took a measurement: "Max Players in the box" is the
    *defending* team's count — its own players in its own penalty area — not the attackers'.
    Counting the tagged team's players in the box it attacks reproduces the organisers' number
    exactly 16 times out of 91; counting its players in the box it defends reproduces it 74
    times out of 91, and lands within one player 90 times out of 91.
    """
    # The claim is about the tagged instances, so its scope is their windows.
    scope_code = phase or "PLAYERS IN THE BOX"
    mask = _scoped_frames(analysis, window, zone, scope_code)
    home_right = attacking_sides(analysis)
    length = analysis.pitch_length_m
    width = analysis.pitch_width_m
    n = analysis.n_frames

    # How many players each team has inside its own penalty area.
    home_in_box = np.zeros(n, dtype=np.int16)
    away_in_box = np.zeros(n, dtype=np.int16)
    for lo in range(0, n, 20000):
        hi = min(n, lo + 20000)
        x = analysis.player_xy[lo:hi, :, 0]
        home_progress = np.where(home_right[lo:hi][:, None], x, length - x)
        away_progress = length - home_progress
        progress = np.where(analysis.teams[lo:hi] == HOME, home_progress, away_progress)
        in_own_box = (
            np.isfinite(progress)
            & (progress < 16.5)
            & (np.abs(analysis.player_xy[lo:hi, :, 1] - width / 2) < 20.3)
        )
        home_in_box[lo:hi] = (in_own_box & (analysis.teams[lo:hi] == HOME)).sum(axis=1).astype(np.int16)
        away_in_box[lo:hi] = (in_own_box & (analysis.teams[lo:hi] == AWAY)).sum(axis=1).astype(np.int16)

    ours = []
    theirs = []
    for instance in phase_tools.by_code(analysis.phases, "PLAYERS IN THE BOX"):
        team = phase_tools.team_index(instance.team)
        stated = instance.labels.get("Max Players in the box", "")
        if team < 0 or not stated.isdigit():
            continue
        block = (home_in_box if team == HOME else away_in_box)[
            max(0, instance.start):min(n, instance.end + 1)
        ]
        if not block.size:
            continue
        ours.append(int(block.max()))
        theirs.append(int(stated))

    matched = min(len(ours), len(theirs))
    exact = sum(1 for i in range(matched) if ours[i] == theirs[i])
    within_one = sum(1 for i in range(matched) if abs(ours[i] - theirs[i]) <= 1)
    detail = [
        ("tagged instances", str(len(ours))),
        ("our peak, median", "{} players".format(int(np.median(ours)) if ours else 0)),
        ("their stated count", "median {} players".format(int(np.median(theirs)) if theirs else 0)),
        ("exact match", "{} of {}".format(exact, matched)),
        ("within one player", "{} of {}".format(within_one, matched)),
    ]
    return Fact(
        id="box_presence",
        title="Players in the box",
        answer="we reproduce the organisers' own count of players in the box exactly {} times "
               "out of {}, and within one player {} times.".format(exact, matched, within_one),
        detail=detail,
        coverage=_coverage_sentence(analysis, mask),
        confidence="the count is over the rectangle of the penalty area and depends on the "
                   "tracker having the players right; the organisers' windows are wide priors "
                   "rather than instants, so a maximum over a wide window is a generous "
                   "comparison",
        evidence="frames {:,}-{:,}".format(*analysis.window(window)),
        scope=_scope_text(window, zone, scope_code),
        coverage_pct=_coverage_pct(analysis, mask),
    )


def annotation_agreement(analysis: Analysis, window: str = "all", zone: str = None,
                      phase: str = None) -> Fact:
    """The check that holds the whole thing up.

    For every code the organisers tagged, how often do our possession labels agree with their
    annotation of who had the ball? No possession ground truth is involved.
    """
    rows = []
    for code in phase_tools.ALL_CODES:
        result = phase_tools.agreement(analysis.phases, code, analysis.labels)
        if not result["instances"]:
            continue
        expected_is_attacker = code in phase_tools.ATTACKING_CODES or code in phase_tools.RESTART_CODES
        rows.append((code, result, expected_is_attacker))

    pairs = phase_tools.mirror_pairs(analysis.phases)
    pair_result = phase_tools.pair_agreement(pairs, analysis.labels)

    detail = []
    for code, result, _ in rows:
        detail.append((code.lower(), "{:.1%} over {:,} frames".format(
            result["agreement"], int(result["frames"]))))
    if pair_result["pairs"]:
        detail.insert(0, ("mirror pairs", "{:.1%} over {:,} frames ({:.0f} pairs)".format(
            pair_result["agreement"], int(pair_result["frames"]), int(pair_result["pairs"]))))

    overall = pair_result["agreement"] if pair_result["frames"] else 0.0
    return Fact(
        id="annotation_agreement",
        title="Agreement with the organisers' own annotation",
        answer="our possession labels agree with the organisers' own phase annotation on "
               "{:.1%} of the frames covered by {} mirror pairs.".format(
                   overall, int(pair_result["pairs"])),
        detail=detail,
        coverage="the annotation is provided data; it is not possession ground truth, and no "
                 "possession labels were used to build it",
        confidence="a mirror pair is an attacking code and a defending code over the same window "
                   "with opposite teams, so the team in possession over that window is stated by "
                   "the organisers",
        evidence="{} instances across {} codes".format(
            len(analysis.phases), len({p.code for p in analysis.phases})),
        scope="the whole match",
        coverage_pct=pair_result["agreement"],
    )


FACT_LIBRARY: Dict[str, Callable[..., Fact]] = {
    # possession
    "possession_share": possession_share,
    "possession_count": possession_count,
    "dead_ball": dead_ball,
    "longest_possession": longest_possession,
    "ball_visibility": ball_visibility,
    "possession_changes": possession_changes,
    "ball_thirds": ball_thirds,
    # tactics
    "build_up": build_up,
    "progression": progression,
    "creating_chances": creating_chances,
    "long_ball": long_ball,
    "attacking_transition": attacking_transition,
    "defensive_transition": defensive_transition,
    "defending_shape": defending_shape,
    "pressing": pressing,
    "restarts": restarts,
    "box_presence": box_presence,
    "annotation_agreement": annotation_agreement,
}
