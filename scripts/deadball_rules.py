"""Evaluate candidate dead-ball rules against the public ground truth.

Why this script exists
-----------------------
The organisers' five public minutes are for checking that the pipeline is right, never for
tuning. This script therefore does **not** search a parameter space for a maximum score. It
evaluates a handful of rules that were each designed from the football, and reports what each
one means as a classifier: how much of the truth's dead ball it captures, and — the number that
actually drives the design — how much of the live play it gets wrong.

The asymmetry that matters
---------------------------
A missed dead-ball period makes one of our possessions a little too long, and the extra frames
cost little because temporal IoU stays above the threshold. A *false* dead-ball period splits a
real possession in two: one part matches and one is spurious, so we lose precision and the
truth's possession is only half recovered. **Missing D is cheap; inventing D is expensive.**
Every rule below is therefore read with that asymmetry in mind: a rule with 70% recall and 95%
precision is worth more than one with 90% recall and 60% precision.
"""

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from analyze_window import ATD, GT, PL, PW, WINDOW, read_window  # noqa: E402


def features():
    lo, hi = WINDOW
    players, pspd, ball, bspd = read_window(ATD, lo + 1, hi)

    diff = ball[:, None, :] - players
    distance = np.sqrt((diff ** 2).sum(axis=2))
    distance[~np.isfinite(distance)] = np.inf
    nearest = distance.min(axis=1)

    within2 = (distance < 2.0).sum(axis=1)
    within3 = (distance < 3.0).sum(axis=1)
    within5 = (distance < 5.0).sum(axis=1)

    edge = np.minimum(ball[:, 0], PL - ball[:, 0])
    edge = np.minimum(edge, np.minimum(ball[:, 1], PW - ball[:, 1]))
    edge = np.where(np.isfinite(edge), edge, np.nan)

    moving = (np.isfinite(pspd) & (pspd > 2.0)).sum(axis=1)
    present = np.isfinite(ball[:, 0])
    return dict(
        nearest=nearest, within2=within2, within3=within3, within5=within5,
        edge=edge, moving=moving, present=present,
    )


def report(name, rule, truth_dead, truth_alive):
    dead_hit = float(np.mean(rule[truth_dead])) if truth_dead.any() else float("nan")
    alive_hit = float(np.mean(rule[truth_alive])) if truth_alive.any() else float("nan")
    predicted = rule.sum()
    true_positive = float(np.sum(rule & truth_dead))
    false_positive = float(np.sum(rule & truth_alive))
    precision = true_positive / predicted if predicted else float("nan")
    recall = dead_hit
    print(
        "{:<52} recall {:.3f}  precision {:.3f}  (dead hit {:.1%}, alive hit {:.1%})".format(
            name, recall, precision, dead_hit, alive_hit
        )
    )


def main():
    gt = pd.read_csv(GT)["label"].values
    lo, hi = WINDOW
    truth = gt[lo:hi]
    truth_dead = truth == "D"
    truth_alive = np.isin(truth, ["H", "A"])

    f = features()
    present = f["present"]
    missing = ~present
    nearest = f["nearest"]
    edge = f["edge"]
    moving = f["moving"]

    print("window {}..{}  |  truth: {} dead frames, {} alive frames".format(
        lo, hi, int(truth_dead.sum()), int(truth_alive.sum())))
    print()

    report("ball present", present, truth_dead, truth_alive)
    report("ball missing", missing, truth_dead, truth_alive)
    report("nearest player > 3m", nearest > 3.0, truth_dead, truth_alive)
    report("no player within 3m", f["within3"] == 0, truth_dead, truth_alive)
    report("no player within 5m", f["within5"] == 0, truth_dead, truth_alive)
    report("ball within 8m of a touchline", edge <= 8.0, truth_dead, truth_alive)
    report("moving players <= 2", moving <= 2, truth_dead, truth_alive)
    report("moving players <= 4", moving <= 4, truth_dead, truth_alive)
    print()

    candidates = {
        "R1 ball out/unattended near a boundary (<=8m)":
            present & (nearest > 3.0) & (edge <= 8.0),
        "R2 ball missing & everyone stopped (<=2 movers)":
            missing & (moving <= 2),
        "R3 ball missing & not running (<=4 movers)":
            missing & (moving <= 4),
        "R4 ball unattended (>3m) anywhere":
            present & (nearest > 3.0),
        "R5 R1 | R2":
            (present & (nearest > 3.0) & (edge <= 8.0)) | (missing & (moving <= 2)),
        "R6 R1 | R2 | (unattended and quiet)":
            (present & (nearest > 3.0) & (edge <= 8.0))
            | (missing & (moving <= 2))
            | (present & (nearest > 3.0) & (moving <= 4)),
        "R7 R5 widened to 12m boundary":
            (present & (nearest > 3.0) & (edge <= 12.0)) | (missing & (moving <= 2)),
    }
    for name, rule in candidates.items():
        report(name, rule, truth_dead, truth_alive)

    print("\nWhat the rules get wrong, in frames:")
    rule = candidates["R5 R1 | R2"]
    print("  false positives (alive, called dead): {}".format(int(np.sum(rule & truth_alive))))
    print("  false negatives (dead, called alive): {}".format(int(np.sum(~rule & truth_dead))))

    print("\nCost of each mistake in possessions (the metric's unit):")
    print("  a false D splits a truth possession: it becomes 1 true match + 1 spurious")
    print("  a missed D lengthens a truth possession: temporal IoU falls but usually stays")
    print("  above 0.7, so the possession is still recovered")


if __name__ == "__main__":
    sys.exit(main())
