"""Which rule for *when* the dead period begins?

Why this exists
---------------
The organisers' clarification email asks it outright:

    *"For a stoppage, does D begin at the infringement, at the whistle, or at the tracking's own
    flag?"*

The ground truth is built from the organisers' **corrected** tracking, whose dead-ball flag we do
not have, so the onset has to be inferred from what we can see. This script measures the three
rules that can be implemented from the provided data and reports what each costs.

The reference used here is **legal**: the Smart Tagging's mirror pairs. For 140 windows the
organisers tag an attacking code and a defending code over the same interval with opposite
teams, which states who had the ball. No possession ground truth is involved, and nothing is
selected on the public five minutes.

What the rules mean
-------------------
``movement`` (the default)
    The dead period begins when the players stop. This is closest to **the whistle**, and it is
    deliberately late: a false dead-ball period splits a real possession in two.
``ball_out``
    The dead period begins when the ball's last observed position is outside the pitch —
    earlier, and independent of what the players are doing.
``earliest``
    Either signal fires. The most inclusive rule, and the closest to **the infringement**.

The third option the organisers mention — *the tracking's own flag* — is the corrected tracking,
which is not in the bundle. If that is the answer, the rule is "whatever the corrected tracking
says", and the honest response is to ask for the export rather than to guess.

What is reported
----------------
For each rule: the possession count and mean length, the fragmentation, the dead-ball share, the
agreement with the mirror pairs, and — for information only, never for selection — the score on
the public five minutes.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mtah.config import AWAY, DEAD, HOME, Config
from mtah.pipeline import decide
from mtah.match import load_match
from plumb import phases as phase_tools

RULES = ("movement", "ball_out", "earliest")


def measure(config: Config) -> Dict[str, float]:
    """Everything the three rules are compared on."""
    match = load_match(config)
    evidence, decision = decide(match, config)

    labels = decision.labels
    graded = evidence.graded
    possessions = [
        (a, b, label) for a, b, label in decision.spells if label in (HOME, AWAY)
    ]
    durations = [(b - a) / 25.0 for a, b, _ in possessions]
    changes = 0
    previous = None
    for _, _, label in possessions:
        if previous is not None and label != previous:
            changes += 1
        previous = label

    pairs = phase_tools.mirror_pairs(match.phases)
    agreement = phase_tools.pair_agreement(pairs, labels)["agreement"]

    return {
        "possessions": len(possessions),
        "mean_length": float(np.mean(durations)) if durations else 0.0,
        "median_length": float(np.median(durations)) if durations else 0.0,
        "fragmentation": changes / max(1, len(possessions)),
        "dead_frames": int((labels[graded] == DEAD).sum()),
        "dead_share": float((labels[graded] == DEAD).mean()) if graded.any() else 0.0,
        "mirror_agreement": agreement,
    }


def main() -> int:
    base = Config(data_dir=os.environ.get("MTAH_DATA_DIR", "data"))
    rows: List[Dict[str, float]] = []
    for rule in RULES:
        config = Config(**{**base.as_dict(), "dead_onset": rule})
        result = measure(config)
        result["rule"] = rule
        rows.append(result)
        print("{:<12} possessions {:>4}   mean {:>5.1f} s   frag {:.2f}   "
              "dead {:>6,} frames ({:>5.1%})   mirror agreement {:.1%}".format(
                  rule, result["possessions"], result["mean_length"],
                  result["fragmentation"], result["dead_frames"], result["dead_share"],
                  result["mirror_agreement"]))
    print()
    print("mirror agreement = the share of the 140 mirror-paired windows in which our possession")
    print("labels match the team the organisers named. It uses no possession ground truth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
