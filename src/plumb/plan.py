"""What would have to be collected to answer a question we cannot answer.

A refusal is only useful if it comes with a way forward, and a way forward is only useful if it
is **specific**: not "get better data" but "these 64,643 frames, of which the longest blackout
is 221.5 seconds near the end of the second half".

Every plan here has four parts:

``collect``
    the item, named.
``how much``
    the size of the gap, measured in this match — frames, seconds, and the share of the claim's
    own scope.
``unlocks``
    what becomes answerable, and what the answer would rest on.
``by when``
    when it could arrive, where that is known.

The numbers in the middle column are the point. "The tracker lost the ball" is a complaint;
"the tracker lost the ball for 64,643 frames, 40.7 % of the graded ones, in one stretch of 221.5
seconds" is a specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from mtah.config import DEAD

from .analysis import Analysis
from .router import Refusal, Route


@dataclass
class Plan:
    """A collection plan: what to collect, how much, what it unlocks, and by when."""

    collect: str
    how_much: str
    unlocks: str
    by_when: str = ""
    steps: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "collect": self.collect,
            "how_much": self.how_much,
            "unlocks": self.unlocks,
            "by_when": self.by_when,
            "steps": list(self.steps),
        }


def _gap_sizes(analysis: Analysis, frames: Optional[np.ndarray] = None) -> dict:
    """How much of the claim's own scope the feed cannot carry."""
    if frames is None:
        frames = np.ones(analysis.n_frames, dtype=bool)
    frames = np.asarray(frames, dtype=bool)
    graded = frames & analysis.evidence.graded
    missing = graded & ~analysis.evidence.ball_present
    total = int(graded.sum())
    lost = int(missing.sum())

    longest = 0
    run = 0
    for index in range(analysis.n_frames):
        if missing[index]:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    unstable = int((graded & ~analysis.coverage().ball_stable).sum())
    duplicates = int((graded & (analysis.coverage().duplicate_players > 0)).sum())
    return {
        "frames": total,
        "missing": lost,
        "missing_pct": (lost / total) if total else 0.0,
        "longest_seconds": longest / analysis.fps,
        "unstable": unstable,
        "duplicates": duplicates,
        "dead": int((frames & (analysis.labels == DEAD)).sum()),
    }


def plan_for(analysis: Analysis, route: Route) -> Plan:
    """The collection plan for a routed question."""
    if route.kind == "refusal":
        return _refusal_plan(analysis, route.detail)
    return _supported_plan(analysis, route)


def _refusal_plan(analysis: Analysis, refusal: Refusal) -> Plan:
    size = _gap_sizes(analysis)
    if refusal.id == "missing_ball":
        return Plan(
            collect="the ball positions for the frames the tracker did not produce",
            how_much="{:,} frames ({:.1%} of the graded ones), in blackouts of up to {:.1f} "
                     "seconds".format(
                         size["missing"], size["missing_pct"], size["longest_seconds"]),
            unlocks="possession inside the blackouts; every other fact in this build already "
                    "stops at the edge of them",
            by_when="the organisers' corrected tracking export, which repairs the same gaps",
            steps=[
                "ask for the corrected tracking export, which the organisers hold",
                "while waiting, report the gap as a hole rather than filling it in",
                "re-run this plan afterwards: the same question becomes answerable, with the "
                "same evidence packet",
            ],
        )
    if refusal.id == "player_identity":
        return Plan(
            collect="an identity-resolved tracking export, or per-player event annotations",
            how_much="all 46 track slots, of which 22 are on the pitch at a time; the "
                     "organisers warn that slots swap identity as the tracker loses people",
            unlocks="every per-player question: who touched it, who passed, who was in the box",
            by_when="the organisers' corrected tracking export",
            steps=[
                "request the corrected tracking export",
                "in the meantime, answer at team level, which is what the data supports",
            ],
        )
    if refusal.id == "event_data":
        return Plan(
            collect="an event feed with timestamps for this match",
            how_much="the whole match: the bundle has 638 tagged phases but no event records",
            unlocks="passes, shots, cards, substitutions, and the goal log",
            by_when="26 November, with the Innovation Challenge dataset",
            steps=[
                "wait for the ten-match dataset and its event schema",
                "in the meantime, the phase annotation already covers build-up, progression, "
                "chances, transitions and restarts",
            ],
        )
    if refusal.id == "other_matches":
        return Plan(
            collect="the ten-match dataset with tracking and event data",
            how_much="ten matches; the method is already written as a library, so the "
                     "collection plan is the data, not the code",
            unlocks="claims across a season rather than across one fixture",
            by_when="26 November, with the Innovation Challenge dataset",
            steps=[
                "point the same code at each of the ten matches",
                "publish the coverage of each claim per match, so a reader can see which "
                "matches carry which aspects",
            ],
        )
    if refusal.id == "ground_truth":
        return Plan(
            collect="the corrected tracking export the organisers score against",
            how_much="not something we can measure: it is the answer key",
            unlocks="nothing we would use; it would make the exercise meaningless",
            by_when="published by the organisers for enrolled participants",
            steps=[
                "request it if the rules allow",
                "in the meantime, our own labels are published with their coverage, which is "
                "the honest version of the same question",
            ],
        )
    if refusal.id == "tactics_claims":
        return Plan(
            collect="a record of the tactical instructions, or a video that shows the shape",
            how_much="one half of one match, at the level of what a coach would draw",
            unlocks="why the shape was what it was, rather than what it was",
            by_when="only a person who was there can answer this",
            steps=[
                "ask a coach who was there",
                "in the meantime, the shape itself is measurable: block width, line height, "
                "press numbers, players in the box",
            ],
        )
    return Plan(
        collect=refusal.missing,
        how_much="see the coverage of this match's feed",
        unlocks=refusal.proxy,
        steps=[refusal.remedy],
    )


def _supported_plan(analysis: Analysis, route: Route) -> Plan:
    """The plan for a question we *can* answer: what would strengthen the answer.

    Measured over the claim's own frames, not the match's: a plan about the final third that
    quotes the match's coverage is the same category error the facts exist to avoid.
    """
    from .facts import _scoped_frames
    from .tactics import tactics_scope

    frames = _scoped_frames(analysis, route.window, route.zone, route.phase)
    size = _gap_sizes(analysis, frames)
    scope = analysis.coverage().scope(frames)
    sensitivity = analysis.coverage().sensitivity(frames)

    return Plan(
        collect="nothing — this question is already answerable",
        how_much="the answer rests on {:,} frames; the feed covers {:.1%} of them and the "
                 "tracker is unstable on {:,} of them".format(
                     scope["frames"], scope["ball_visibility"], size["unstable"]),
        unlocks="the claim is already supported; {:,} frames of its own scope ({:.1%}) would "
                "strengthen it further".format(size["missing"], size["missing_pct"]),
        by_when="the corrected tracking export would close the remaining gap",
        steps=[
            "quote the coverage with the answer, as this build does",
            "if the claim must be carried further, collect the frames where the ball is not "
            "observed",
            "watch the sensitivity: {:.1%} of the claim's own frames were decided by less "
            "than half a metre".format(sensitivity),
        ],
    )
