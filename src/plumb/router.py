"""Route a question to a fact, or refuse it.

Two kinds of rule, and the refusals come first, because a refusal is a statement about what the
data can bear, and it has to be checked before anything else is answered.

**The router is rules, not a model.** On purpose: the pitch is that every claim is deterministic
and reproducible, so the machine that decides *which* claim is on the table must be deterministic
too — and a rule set can be read, argued with and audited in a way a prompt cannot.

Every refusal carries three things: **why** the data cannot support the question, **what is
missing**, and the **nearest answerable proxy**. A refusal without a remedy is a dead end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .facts import Fact


@dataclass
class Refusal:
    """A question the data cannot support — said precisely, with a way forward."""

    id: str
    title: str
    why: str
    missing: str
    remedy: str
    proxy: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "why": self.why,
            "missing": self.missing,
            "remedy": self.remedy,
            "proxy": self.proxy,
        }


def _matches(question: str, patterns: List[str]) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


# --------------------------------------------------------------------------------------------------
# Refusals — checked first, because they are about capability rather than about content
# --------------------------------------------------------------------------------------------------

REFUSAL_RULES: List[Tuple[str, str, List[str], str, str, str, str]] = [
    (
        "player_identity",
        "per-player questions",
        [
            r"\bwhich player\b", r"\bwho (touched|passed|scored)\b", r"\bplayer (with|who|that)\b",
            r"\bbest player\b", r"\btop player\b", r"\bper[- ]player\b", r"\bplayer's\b",
            r"\bhow many passes did\b", r"\bwho has the most touches\b", r"\bindividual\b",
        ],
        "the tracking has no player identities: 46 anonymous track slots for 22 players on the "
        "pitch, and the organisers warn that slots swap identity as the tracker loses and "
        "re-acquires people. A slot is not a person.",
        "an identity-resolved tracking export, or per-player event annotations for this match.",
        "identity resolution from a corrected export (the organisers' corrected tracking), or the "
        "event annotations that arrive with the Innovation Challenge dataset.",
        "team-level facts: possession share, possession count and length, dead-ball time, where "
        "the ball was, and the coverage of the feed itself.",
    ),
    (
        "event_data",
        "event-level questions",
        [
            r"\bhow many (passes|shots|corners|fouls|cards|saves)\b", r"\bpass count\b",
            r"\bsubstitut", r"\bhow many times did .* (pass|shot|cross)\b", r"\bwas there a card\b",
            r"\bwho scored\b", r"\bthe goal\b", r"\bshots? on target\b", r"\bchance\b",
        ],
        "this bundle carries automatic tracking and automatic phase tagging, but no event feed "
        "with timestamps. Passes, shots, cards and substitutions are not in the data we were "
        "given — inferring them from tracking is a different project with its own error bars.",
        "an event feed with timestamps for this match.",
        "the organisers' event annotations, which arrive with the Innovation Challenge dataset; "
        "external event data for other matches is allowed, provided it is cited.",
        "possession spells and their boundaries: where possession began, ended and changed hands, "
        "with the coverage behind each one.",
    ),
    (
        "ground_truth",
        "questions about the answer key",
        [
            r"\bground truth\b", r"\bthe correct answer\b", r"\bwhat does the referee\b",
            r"\bthe official labels?\\b", r"\bthe hidden (labels?|truth)\b", r"\bwhat (is|was) the "
            r"right (label|answer)\b",
        ],
        "the labels we are scored against are the organisers' *corrected* tracking, which is not "
        "in the bundle we were given. Asking us to state them is asking for the answer key, and "
        "we will not reconstruct it from the public five minutes — those may be used to check the "
        "pipeline, not to fit it.",
        "the corrected tracking export, which the organisers hold.",
        "requesting it from the organisers, who publish it for enrolled participants.",
        "our own labels, published with their coverage: the same question, answered from the "
        "data we actually have.",
    ),
    (
        "other_matches",
        "questions about other games",
        [
            r"\bother (matches?|games?|fixtures)\b", r"\bthe season\b", r"\bleague table\b",
            r"\bother teams?\b", r"\ball matches\b", r"\bten matches\b", r"\binnovation challenge "
            r"dataset\b",
        ],
        "the bundle is one match: FC Barcelona v Athletic Club, tactical recording. Nothing here "
        "generalises to another fixture, and we will not pretend otherwise.",
        "the ten-match dataset with tracking and event data, released on 26 November.",
        "waiting for the Innovation Challenge dataset — or building the method so it applies to "
        "any match, which is the point of writing it as a library.",
        "the facts of this match, and the coverage that says how far they can be carried.",
    ),
    (
        "missing_ball",
        "questions about the moments the feed cannot see",
        [
            r"\bwhile the ball was missing\b", r"\bduring the gap\b", r"\bwhen the ball was not "
            r"tracked\b", r"\bwhat happened (while|during) the (blackout|gap)\b",
            r"\bin the (untracked|blind) (window|stretch|period)\b",
        ],
        "for stretches of more than a minute the ball is not tracked at all — the longest is "
        "around three minutes and a half near the end of the second half. Nothing about "
        "possession in those frames can be supported, because there is no observation to support "
        "it.",
        "the ball positions for those frames, which the tracker did not produce.",
        "the organisers' corrected tracking export, which repairs the same gaps.",
        "the possession either side of the gap, with the gap itself reported as a hole rather "
        "than filled in.",
    ),
]

# --------------------------------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------------------------------

FACT_RULES: List[Tuple[str, List[str]]] = [
    ("possession_share", [
        r"possession share", r"share of possession", r"who had (more|the) possession",
        r"possession (percentage|%)", r"who dominated", r"possession split",
    ]),
    ("possession_count", [
        r"how many possessions", r"number of possessions", r"possession count",
        r"how long (are|were) possessions", r"possession length", r"how many spells",
    ]),
    ("dead_ball", [
        r"dead ball", r"how long was the ball dead", r"stoppage", r"time out of play",
        r"how much of the match was dead", r"ball not in play",
    ]),
    ("longest_possession", [
        r"longest possession", r"longest spell", r"longest run of possession",
    ]),
    ("ball_visibility", [
        r"visibility", r"coverage", r"how much of (the|this) (match|data)", r"how much can we see",
        r"ball tracked", r"how much of the (data|match) is usable", r"how reliable",
        r"can we (actually )?see",
    ]),
    ("possession_changes", [
        r"changes? of possession", r"how often did possession change", r"turnovers",
        r"how many hand[- ]?overs", r"how many times did possession",
    ]),
    ("ball_thirds", [
        r"which third", r"where was the ball", r"what part of the pitch", r"ball position",
        r"which part of the pitch",
    ]),
]

WINDOW_RULES: List[Tuple[str, List[str]]] = [
    ("first-half", [r"first half", r"1st half"]),
    ("second-half", [r"second half", r"2nd half"]),
    ("halftime", [r"half ?time", r"the break"]),
    ("all", [r"whole match", r"the match", r"entire match", r"overall", r"all of it"]),
]


def window_of(question: str) -> str:
    """Which window the question is about."""
    for name, patterns in WINDOW_RULES:
        if _matches(question, patterns):
            return name
    return "all"


@dataclass
class Route:
    """Where a question landed."""

    kind: str  # "fact" | "refusal" | "unknown"
    id: Optional[str] = None
    window: str = "all"
    question: str = ""
    detail: Optional[object] = field(default=None)


def route(question: str) -> Route:
    """Send a question to a fact or to a refusal."""
    window = window_of(question)

    for refusal_id, title, patterns, why, missing, remedy, proxy in REFUSAL_RULES:
        if _matches(question, patterns):
            return Route(
                kind="refusal",
                id=refusal_id,
                window=window,
                question=question,
                detail=Refusal(
                    id=refusal_id,
                    title=title,
                    why=why,
                    missing=missing,
                    remedy=remedy,
                    proxy=proxy,
                ),
            )

    for fact_id, patterns in FACT_RULES:
        if _matches(question, patterns):
            return Route(kind="fact", id=fact_id, window=window, question=question)

    return Route(kind="unknown", window=window, question=question)


def answerable_questions() -> List[Tuple[str, str]]:
    """The questions this build can answer, for the 'I can answer these' list."""
    return [
        ("possession_share", "who had more of the ball"),
        ("possession_count", "how many possessions, and how long"),
        ("dead_ball", "how much of the match was dead ball"),
        ("longest_possession", "the longest single possession"),
        ("ball_visibility", "how much of the match the feed can carry"),
        ("possession_changes", "how often possession changed hands"),
        ("ball_thirds", "where the ball was, by third"),
    ]
