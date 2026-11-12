"""Spell-level diagnosis: which possessions do we recover, and which do we break?

The scorer reports a number; this script reports the *reasons*. For every possession in the
public ground truth it finds the best-matching predicted possession and its temporal IoU, and
then it says what kind of mistake each failure is:

* **split** — the truth's possession is covered by more than one of ours;
* **merged** — one of ours covers more than one of the truth's;
* **shifted** — the right number of possessions, but the boundaries are off;
* **missing** — no prediction overlaps it at all;
* **spurious** — one of ours matches nothing.

This is diagnostics, not tuning: it tells us which mechanism is broken, and we fix the mechanism.
"""

import sys

import numpy as np
import pandas as pd

OFFICIAL = "/private/var/folders/pv/x_b_3fy12z9g3bxv14wl5jv80000gn/T/opencode/mth2027"
sys.path.insert(0, OFFICIAL + "/evaluation")
import possession_metrics as pm  # noqa: E402

GT = OFFICIAL + "/evaluation/gt/BAR-ATH_possession_gt_public.csv"
OURS = "artifacts/submission.csv"
WINDOW = (11185, 18685)


def main():
    gt = pm.label_codes(pm.read_label_csv(GT))
    ours = pm.label_codes(pm.read_label_csv(OURS))
    runs = pm.valid_runs(gt)

    gt_spells = pm.possession_spells(gt, runs)
    our_spells = pm.possession_spells(ours, runs)

    print("truth: {} possessions | ours: {} possessions".format(len(gt_spells), len(our_spells)))
    print()

    overlaps = pm.spell_overlaps(gt_spells, our_spells)

    print("each truth possession and the best predicted possession covering it:")
    print("{:<6} {:<7} {:>7} {:>7} {:>8} {:>8}  {}".format(
        "start", "team", "len_s", "cover", "best_IoU", "ours_len", "our_start"))
    unmatched_truth = 0
    for index, (gs, ge, gc) in enumerate(gt_spells):
        candidates = [(iou, j) for iou, i, j in overlaps if i == index]
        if candidates:
            best_iou, j = max(candidates)
            os_, oe, oc = our_spells[j]
            cover = float(np.sum(ours[gs:ge] == (0 if gc == 0 else 1)) / (ge - gs))
            print("{:<6} {:<7} {:>7.1f} {:>7.1%} {:>8.2f} {:>8.1f}  {}".format(
                gs, "H" if gc == 0 else "A", (ge - gs) / 25.0, cover, best_iou,
                (oe - os_) / 25.0, os_))
        else:
            unmatched_truth += 1
            print("{:<6} {:<7} {:>7.1f} {:>7} {:>8} {:>8}  {}".format(
                gs, "H" if gc == 0 else "A", (ge - gs) / 25.0, "-", "-", "-", "NO OVERLAP"))

    print("\ntruth possessions with no overlapping prediction: {}".format(unmatched_truth))

    used = set()
    for iou, i, j in overlaps:
        if iou >= 0.3:
            used.add(j)
    spurious = [j for j in range(len(our_spells)) if j not in used]
    print("our possessions with no truth possession at IoU>=0.3: {}".format(len(spurious)))
    for j in spurious:
        os_, oe, oc = our_spells[j]
        print("   start {:<7} team {} len {:5.1f}s".format(
            os_, "H" if oc == 0 else "A", (oe - os_) / 25.0))

    # How many of our possessions *overlap* a truth possession at all?
    overlapping = {j for _, _, j in overlaps}
    print("\nour possessions overlapping anything: {} of {}".format(len(overlapping), len(our_spells)))

    # Dead ball: how much of it do we get, in the window?
    window = slice(WINDOW[0], WINDOW[1])
    gt_dead = int(np.sum(gt[window] == pm.D))
    our_dead = int(np.sum(ours[window] == pm.D))
    print("\ndead ball in the public window: truth {} frames, ours {} frames".format(gt_dead, our_dead))
    print("  ours dead but truth alive: {}".format(
        int(np.sum((ours[window] == pm.D) & ((gt[window] == pm.H) | (gt[window] == pm.A))))))
    print("  truth dead but ours alive: {}".format(
        int(np.sum((gt[window] == pm.D) & (ours[window] != pm.D)))))

    # Our dead-ball blocks across the whole match: length distribution.
    dead_runs = [(a, b) for a, b, label in pm.segments(ours, pm.valid_runs(ours)) if label == pm.D]
    lengths = sorted(((b - a) / 25.0 for a, b in dead_runs), reverse=True)
    print("\nour dead-ball blocks across the match: {} (longest: {})".format(
        len(dead_runs), [round(x, 1) for x in lengths[:12]]))
    short = sum(1 for x in lengths if x < 2.0)
    print("  blocks shorter than 2s: {}".format(short))


if __name__ == "__main__":
    sys.exit(main())
