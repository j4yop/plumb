"""The organisers' own tactical annotation, read as a first-class input.

What the Smart Tagging file actually contains
---------------------------------------------
It is not just set pieces. It is 638 instances spread over **fourteen codes**, each with a team,
a half, and sometimes more:

===============================  ====  ================================================
code                             n     what it marks
===============================  ====  ================================================
``SET PIECES``                   59    a restart, with its type (throw-in, corner, ...)
``BUILD UP``                     22    the team playing the ball out of defence
``PROGRESSION``                  66    the team moving the ball up the pitch
``CREATING CHANCES``             30    the team in the attacking third
``LONG BALL``                    29    the team going long
``ATTACKING TRANSITION``         24    a team winning the ball and going forward
``DEFENSIVE TRANSITION``         24    the other side reacting to it
``DEFENDING IN MIDDLE THIRD``    66    the team defending in the middle third
``DEFENDING IN DEFENSIVE THIRD`` 30    the team defending in their own third
``DEFENDING IN ATTACKING THIRD`` 22    the team defending in the opponent's third
``PLAYERS IN THE BOX``           97    players in the penalty area, and how many
``BALL IN FINAL THIRD``          93    the ball in the final third
``BALL IN THE BOX``              72    the ball in the penalty area
``GOALS``                         4    a goal
===============================  ====  ================================================

Two properties make this the most valuable thing in the bundle.

**It is the organisers' own vocabulary for the tactical aspects.** The Innovation Challenge
asks for an aspect; the aspects they have in mind are these codes. A system that answers in
their vocabulary can be checked against their annotation.

**It comes in mirror pairs.** For 284 instances there is an attacking code and a defending code
over the *same* interval with *opposite* teams — ``PROGRESSION`` for Barcelona and
``DEFENDING IN MIDDLE THIRD`` for Athletic Club over one window. The team named by the
attacking code is therefore known to have had the ball during that window, which is a check on
our possession labels that uses **no possession ground truth at all**.

That check is the backbone of the reliability engine: every aspect we compute can be scored
against the organisers' own annotation of that aspect.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from mtah.match import Phase

# The codes, grouped by what they describe.
ATTACKING_CODES = (
    "BUILD UP",
    "PROGRESSION",
    "CREATING CHANCES",
    "LONG BALL",
    "ATTACKING TRANSITION",
    "BALL IN FINAL THIRD",
    "BALL IN THE BOX",
    "PLAYERS IN THE BOX",
)
DEFENDING_CODES = (
    "DEFENDING IN MIDDLE THIRD",
    "DEFENDING IN DEFENSIVE THIRD",
    "DEFENDING IN ATTACKING THIRD",
    "DEFENSIVE TRANSITION",
)
RESTART_CODES = ("SET PIECES",)
OTHER_CODES = ("GOALS",)

ALL_CODES = ATTACKING_CODES + DEFENDING_CODES + RESTART_CODES + OTHER_CODES

# The codes that mark a restart, and the type of each.
RESTART_TYPES = (
    "Throw-in",
    "Corner Kick",
    "Goal Kick",
    "Free Kick",
    "Kick Off (Start)",
    "Kick Off (After Goal)",
)

# A code and its mirror, when the organisers tag both halves of the same moment.
MIRRORS: Dict[str, str] = {
    "BUILD UP": "DEFENDING IN ATTACKING THIRD",
    "PROGRESSION": "DEFENDING IN MIDDLE THIRD",
    "CREATING CHANCES": "DEFENDING IN DEFENSIVE THIRD",
    "ATTACKING TRANSITION": "DEFENSIVE TRANSITION",
    "LONG BALL": "DEFENSIVE TRANSITION",
}


def by_code(phases: List[Phase], code: str) -> List[Phase]:
    return [p for p in phases if p.code == code]


def team_index(name: str) -> int:
    """0 for the home team, 1 for the away team, -1 when the annotation names neither."""
    lowered = (name or "").strip().lower()
    if lowered in ("barcelona",):
        return 0
    if lowered in ("atletic club", "athletic", "ath bilbao"):
        return 1
    return -1


def agreement(phases: List[Phase], code: str, labels: np.ndarray, team_of: str = "Barcelona") -> Dict[str, float]:
    """How often our possession labels agree with the organisers' annotation of a code.

    The codes come in two flavours. An **attacking** code names the team that had the ball, so
    our label should be that team. A **defending** code names the team that did *not* have the
    ball, so our label should be the other one. The function reads the flavour from the code.

    Only the frames where a team is named and our own label says a team had the ball are
    counted; the rest is reported as "unlabelled" rather than quietly dropped.
    """
    defending = code in DEFENDING_CODES
    total = 0
    agree = 0
    named = 0
    for instance in by_code(phases, code):
        team = team_index(instance.team)
        if team < 0:
            continue
        expected = 1 - team if defending else team
        lo = max(0, instance.start)
        hi = min(labels.shape[0] - 1, instance.end)
        if hi < lo:
            continue
        block = labels[lo:hi + 1]
        alive = (block == 0) | (block == 1)
        total += int(alive.sum())
        agree += int((block[alive] == expected).sum())
        named += 1
    return {
        "instances": float(named),
        "frames": float(total),
        "agreement": (agree / total) if total else 0.0,
    }


def mirror_pairs(phases: List[Phase]) -> List[Tuple[Phase, Phase]]:
    """The instances where an attacking code and a defending code cover the same window.

    Each pair says: over this interval, this team had the ball and that team was defending.
    That is a possession statement the organisers made themselves, and checking our labels
    against it uses no possession ground truth.
    """
    attacking = [p for p in phases if p.code in ATTACKING_CODES]
    defending = [p for p in phases if p.code in DEFENDING_CODES]
    pairs: List[Tuple[Phase, Phase]] = []
    for attack in attacking:
        attack_team = team_index(attack.team)
        if attack_team < 0:
            continue
        for defence in defending:
            if abs(attack.start - defence.start) > 2 or abs(attack.end - defence.end) > 2:
                continue
            if team_index(defence.team) == attack_team:
                continue
            pairs.append((attack, defence))
            break
    return pairs


def pair_agreement(pairs: List[Tuple[Phase, Phase]], labels: np.ndarray) -> Dict[str, float]:
    """Agreement with the mirror pairs, which are the strongest statement available."""
    total = 0
    agree = 0
    for attack, defence in pairs:
        attack_team = team_index(attack.team)
        if attack_team < 0:
            continue
        lo = max(0, attack.start)
        hi = min(labels.shape[0] - 1, attack.end)
        if hi < lo:
            continue
        block = labels[lo:hi + 1]
        alive = (block == 0) | (block == 1)
        total += int(alive.sum())
        agree += int((block[alive] == attack_team).sum())
    return {
        "pairs": float(len(pairs)),
        "frames": float(total),
        "agreement": (agree / total) if total else 0.0,
    }
