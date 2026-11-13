"""Route a question to a fact, or refuse it.

Two kinds of rule, and the refusals come first, because a refusal is a statement about what the
data can bear, and it has to be checked before anything else is answered.

**The router is rules, not a model.** On purpose: the pitch is that every claim is deterministic
and reproducible, so the machine that decides *which* claim is on the table must be deterministic
too — and a rule set can be read, argued with and audited in a way a prompt cannot.

Every refusal carries four things: **why** the data cannot support the question, **what is
missing**, the **remedy** that would close the gap, and the **nearest answerable proxy**. A
refusal without a remedy is a dead end.

The rules are also aware of the *scope* a question is about — the window, the zone, and the
tactical phase — so that "how much of the final third can we see" is answered about the final
third and not about the match.
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
            r"\bwho (was|were) (the )?(goalkeeper|keeper|striker|defender|midfielder)\b",
        ],
        "the tracking has no player identities: 46 anonymous track slots for 22 players on the "
        "pitch, and the organisers warn that slots swap identity as the tracker loses and "
        "re-acquires people. A slot is not a person.",
        "an identity-resolved tracking export, or per-player event annotations for this match.",
        "request the organisers' corrected tracking export, which resolves the slots; in the "
        "meantime the team-level facts below answer every question of the same shape",
        "team-level facts: possession share, possession count and length, dead-ball time, where "
        "the ball was, and the coverage of the feed itself.",
    ),
    (
        "event_data",
        "event-level questions",
        [
            r"\bhow many (passes|shots|fouls|cards|saves)\b", r"\bpass count\b",
            r"\bsubstitut", r"\bhow many times did .* (pass|shot|cross)\b", r"\bwas there a card\b",
            r"\bhow many (offside|saves|yellow|red)\b",
            r"\bwho scored\b", r"\bthe goal\b", r"\bshots? on target\b", r"\bchance\b",
            r"\bhow many goals\b", r"\bgoal difference\b", r"\bclean sheet\b",
        ],
        "this bundle carries automatic tracking and automatic phase tagging, but no event feed "
        "with timestamps. Passes, shots, cards and substitutions are not in the data we were "
        "given — inferring them from tracking is a different project with its own error bars.",
        "an event feed with timestamps for this match.",
        "the event annotations that arrive with the Innovation Challenge dataset on 26 November; "
        "external event data for other matches is allowed, provided it is cited",
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
            r"dataset\b", r"\bthe (upcoming|other) data\b",
        ],
        "the bundle is one match: FC Barcelona v Athletic Club, tactical recording. Nothing here "
        "generalises to another fixture, and we will not pretend otherwise.",
        "the ten-match dataset with tracking and event data, released on 26 November.",
        "wait for the Innovation Challenge dataset, or extend the method so it applies to any "
        "match — which is the point of writing it as a library rather than a script",
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
        "the organisers' corrected tracking export, which repairs the same gaps; failing that, a "
        "second camera angle on the same match, which would see what this one lost",
        "the possession either side of the gap, with the gap itself reported as a hole rather "
        "than filled in.",
    ),
    (
        "tactics_claims",
        "questions about what the team *intended*",
        [
            r"\bwhat (was|were) (the team|the players|the coach) (trying|intending|looking)\b",
            r"\bwhy did (the team|the players|they) (play|do that|pass)\b",
            r"\bwhat (was|were) the (game plan|strategy|instructions)\b",
            r"\bhow did the (coach|manager) (want|intend|plan)\b",
            r"\bwhat formation\b", r"\bwere they playing a 4-\d",
        ],
        "tracking says where the players were, not what they meant. An intention is not a "
        "measurement, and any system that reports one is reading tea leaves — which is exactly "
        "the failure mode this project exists to avoid.",
        "a record of the tactical instructions, or a video that shows the shape clearly enough "
        "for a human to judge it.",
        "ask a coach who was there, or ask for the video of the shape; in the meantime, the "
        "measures below are what the data can carry",
        "the shape of the team, measured: block width, line height, press numbers, and how "
        "many players were in the box.",
    ),
]

# --------------------------------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------------------------------

FACT_RULES: List[Tuple[str, List[str]]] = [
    ("annotation_agreement", [
        r"agreement with the (organisers|organizers|smart tagging|annotation)",
        r"do we agree with", r"how well do we (agree|match)",
        r"are we (right|accurate)", r"validation", r"how accurate",
    ]),
    ("possession_share", [
        r"possession share", r"share of possession", r"who had (more|the) possession",
        r"possession (percentage|%)", r"who dominated", r"possession split",
        r"who had the ball", r"which team had (more|the) ball",
    ]),
    ("possession_count", [
        r"how many possessions", r"number of possessions", r"possession count",
        r"how long (are|were) possessions", r"possession length", r"how many spells",
        r"how long was the longest",
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
        r"can we (actually )?see", r"how good is the (data|feed|tracking)",
    ]),
    ("possession_changes", [
        r"changes? of possession", r"how often did possession change", r"turnovers",
        r"how many hand[- ]?overs", r"how many times did possession",
    ]),
    ("ball_thirds", [
        r"which third", r"where was the ball", r"what part of the pitch", r"ball position",
        r"which part of the pitch", r"where was the ball spent",
    ]),
    ("build_up", [
        r"build[- ]?up", r"how did (they|we) (play|build) (out|up)", r"playing out",
        r"line height", r"how high (was|did) the (line|team) (play|stand)",
    ]),
    ("progression", [
        r"progression", r"progress(?:ion)? up the pitch", r"how far did (they|we) (advance|progress)",
        r"carried the ball", r"moved the ball forward",
    ]),
    ("creating_chances", [
        r"creat\w* chances?", r"chance creation", r"final third", r"entries into the (box|penalty)",
        r"how often did (they|we) (get|reach) (to|into) the (box|final third)",
    ]),
    ("long_ball", [
        r"long ball", r"long balls", r"how often did (they|we) go long",
        r"played (it )?long",
    ]),
    ("pressing", [
        r"\bpress(?:ing|ure)?\b", r"did the press win", r"how hard did (they|we) press",
        r"how quickly did (they|we) win it back", r"counter[- ]press", r"press numbers",
    ]),
    ("attacking_transition", [
        r"attacking transition", r"counter attack", r"counter[- ]attack", r"break(?:ing)? (out|away)",
        r"what happened after (they|we) won the ball",
    ]),
    ("defensive_transition", [
        r"defensive transition", r"how long after losing the ball",
        r"did they win it straight back", r"counter[- ]attack defence",
    ]),
    ("defending_shape", [
        r"defend\w* (shape|block|line)", r"block width", r"compact", r"how compact",
        r"how wide was the (defence|defense|block)", r"biggest gap", r"defensive shape",
        r"how did (they|we) defend",
    ]),
    ("restarts", [
        r"restart", r"set[- ]?piece", r"throw[- ]?in", r"corner", r"goal kick", r"free kick",
        r"how many (corners|throw[- ]?ins)", r"kick[- ]?off",
    ]),
    ("box_presence", [
        r"players in the box", r"how many players (were )?in the (box|penalty area)",
        r"occupancy of the box",
    ]),
]

WINDOW_RULES: List[Tuple[str, List[str]]] = [
    ("first-half", [r"first half", r"1st half"]),
    ("second-half", [r"second half", r"2nd half"]),
    ("halftime", [r"half ?time", r"the break"]),
    ("all", [r"whole match", r"the match", r"entire match", r"overall", r"all of it"]),
]

# The tactical phases the organisers' own annotation uses. A question may name one.
PHASE_RULES: List[Tuple[str, List[str]]] = [
    ("BUILD UP", [r"build[- ]?up phase", r"building up", r"playing out"]),
    ("PROGRESSION", [r"progression phase", r"progressive phase"]),
    ("CREATING CHANCES", [r"creating chances phase", r"chance[- ]creation phase"]),
    ("LONG BALL", [r"long ball phase"]),
    ("ATTACKING TRANSITION", [r"attacking transition phase"]),
    ("DEFENSIVE TRANSITION", [r"defensive transition phase"]),
    ("DEFENDING IN MIDDLE THIRD", [r"defending in (the )?middle third phase"]),
    ("DEFENDING IN DEFENSIVE THIRD", [r"defending in (the )?defensive third phase"]),
    ("DEFENDING IN ATTACKING THIRD", [r"defending in (the )?attacking third phase"]),
    ("PLAYERS IN THE BOX", [r"players in the box phase"]),
    ("BALL IN FINAL THIRD", [r"ball in (the )?final third phase"]),
    ("BALL IN THE BOX", [r"ball in (the )?box phase"]),
    ("SET PIECES", [r"set piece phase"]),
]

# Zones: the part of the pitch a claim can be about.
ZONE_RULES: List[Tuple[str, List[str]]] = [
    ("attacking-third", [r"final third", r"attacking third", r"last third"]),
    ("middle-third", [r"middle third", r"central third"]),
    ("defensive-third", [r"defensive third", r"own third", r"first third"]),
    ("box", [r"\bbox\b", r"penalty area", r"the box", r"inside the area"]),
    ("left-channel", [r"left channel", r"left side"]),
    ("right-channel", [r"right channel", r"right side"]),
    ("centre", [r"\bcentre\b", r"\bcenter\b", r"central channel"]),
]


def window_of(question: str) -> str:
    """Which window the question is about."""
    for name, patterns in WINDOW_RULES:
        if _matches(question, patterns):
            return name
    return "all"


def zone_of(question: str) -> Optional[str]:
    """Which part of the pitch the question is about, if it names one."""
    for name, patterns in ZONE_RULES:
        if _matches(question, patterns):
            return name
    return None


def phase_of(question: str) -> Optional[str]:
    """Which tactical phase the question is about, if it names one."""
    for code, patterns in PHASE_RULES:
        if _matches(question, patterns):
            return code
    return None


@dataclass
class Route:
    """Where a question landed."""

    kind: str  # "fact" | "refusal" | "unknown"
    id: Optional[str] = None
    window: str = "all"
    zone: Optional[str] = None
    phase: Optional[str] = None
    question: str = ""
    detail: Optional[object] = field(default=None)


def route(question: str) -> Route:
    """Send a question to a fact or to a refusal."""
    window = window_of(question)
    zone = zone_of(question)
    phase = phase_of(question)

    for refusal_id, title, patterns, why, missing, remedy, proxy in REFUSAL_RULES:
        if _matches(question, patterns):
            return Route(
                kind="refusal",
                id=refusal_id,
                window=window,
                zone=zone,
                phase=phase,
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
            return Route(
                kind="fact", id=fact_id, window=window, zone=zone, phase=phase, question=question
            )

    return Route(kind="unknown", window=window, zone=zone, phase=phase, question=question)


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
        ("build_up", "how the team played out of defence"),
        ("progression", "how far the ball was carried up the pitch"),
        ("creating_chances", "entries into the final third and the box"),
        ("long_ball", "how often the ball was played long"),
        ("attacking_transition", "what happened after a team won the ball"),
        ("defensive_transition", "how often the counter-press won it back"),
        ("defending_shape", "the shape of the team defending"),
        ("pressing", "how hard the press was, and whether it worked"),
        ("restarts", "set pieces taken and kept"),
        ("box_presence", "how many players were in the box"),
        ("annotation_agreement", "how well we agree with the organisers' own annotation"),
    ]
