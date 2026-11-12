"""What the submission says about itself.

The official scorer reports numbers on the *private* ground truth, and the public five minutes are
for checking correctness only. What we are allowed to optimise is what we can measure ourselves:
how many possessions we claim, how long they are, how fragmented they are, how much of the match
we could not see, and how the labels distribute across the phases.

Those numbers are the honest signal, and they are what the technical document reports.
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np

from .config import (
    ABSENCE_NAMES,
    Config,
    DEAD,
    HALF_TIME,
    LABEL_NAMES,
    PHASE_NAMES,
    PRE_MATCH,
    POST_MATCH,
)


def _spells_of(labels: np.ndarray) -> List[tuple]:
    """(start, stop, label) runs of the label sequence, half-open."""
    if labels.size == 0:
        return []
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [labels.size]))
    return [(int(a), int(b), int(labels[a])) for a, b in zip(starts, stops)]


def summarise(labels: np.ndarray, evidence, config: Config, spells=None) -> Dict:
    """A JSON-ready summary of one run."""
    if spells is None:
        spells = _spells_of(labels)

    counts = {name: int(np.sum(labels == index)) for index, name in enumerate(LABEL_NAMES)}
    total = int(labels.size)

    possessions = [(a, b) for a, b, label in spells if label in (0, 1)]
    durations = [(b - a) / 25.0 for a, b in possessions]
    dead_spells = [(a, b) for a, b, label in spells if label == DEAD]

    alive = counts["H"] + counts["A"]
    graded = int(evidence.graded.sum())
    graded_labels = labels[evidence.graded]
    graded_counts = {
        name: int(np.sum(graded_labels == index)) for index, name in enumerate(LABEL_NAMES)
    }

    absence_counts = {
        ABSENCE_NAMES[index]: int(np.sum(evidence.absence_class == index))
        for index in sorted(ABSENCE_NAMES)
    }

    by_phase = {}
    for index, name in enumerate(PHASE_NAMES):
        mask = evidence.phase == index
        if not mask.any():
            continue
        by_phase[name] = {
            "frames": int(mask.sum()),
            "ball_present_pct": round(100.0 * float(evidence.ball_present[mask].mean()), 2),
            "mean_players": round(
                float((evidence.players_home[mask] + evidence.players_away[mask]).mean()), 2
            ),
            "mean_activity_mps": (
                None
                if np.all(np.isnan(evidence.activity[mask]))
                else round(float(np.nanmean(evidence.activity[mask])), 3)
            ),
        }

    return {
        "frames": total,
        "graded_frames": graded,
        "label_counts": counts,
        "label_counts_graded": graded_counts,
        "label_share_graded": {
            name: round(100.0 * graded_counts[name] / max(1, graded), 2) for name in LABEL_NAMES
        },
        "possessions": len(possessions),
        "mean_possession_s": round(float(np.mean(durations)), 2) if durations else 0.0,
        "median_possession_s": round(float(np.median(durations)), 2) if durations else 0.0,
        "max_possession_s": round(float(np.max(durations)), 2) if durations else 0.0,
        "dead_spells": len(dead_spells),
        "dead_seconds": round(sum((b - a) / 25.0 for a, b in dead_spells), 1),
        "home_share_of_alive": round(counts["H"] / alive, 4) if alive else 0.0,
        "absence_classes": absence_counts,
        "coverage": {
            "ball_present_frames": int(evidence.ball_present.sum()),
            "ball_present_pct": round(100.0 * float(evidence.ball_present.mean()), 2),
            "ball_present_pct_graded": round(
                100.0 * float(evidence.ball_present[evidence.graded].mean()), 2
            ),
            "mean_activity_mps_graded": (
                None
                if np.all(np.isnan(evidence.activity[evidence.graded]))
                else round(float(np.nanmean(evidence.activity[evidence.graded])), 3)
            ),
        },
        "by_phase": by_phase,
    }
