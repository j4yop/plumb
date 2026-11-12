"""Read the public ground truth to understand what its labels mean.

This is the *only* permitted use of the five public minutes: check that our pipeline is aligned
and that we understand the semantics. It is not a tuning set — no threshold is chosen by looking
at a score here.

The questions this script answers:

1. What distinguishes a frame the organisers call ``D`` from one they call alive, given that the
   ball is *visible* in most dead-ball frames?
2. At a genuine change of possession, what does the geometry look like? (To separate "the ball
   transferred to the opponent" from "the ball passed near the opponent".)
"""

import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

GT = (
    "/private/var/folders/pv/x_b_3fy12z9g3bxv14wl5jv80000gn/T/opencode/mth2027/"
    "evaluation/gt/BAR-ATH_possession_gt_public.csv"
)
ATD = "data/tactical/BAR-ATH_tactical_atd.txt"
SMART = "data/tactical/BAR-ATH_tactical_smart_tagging.xml"
WINDOW = (11185, 18685)
PL, PW = 105.3, 68.0


def parse_group(group):
    if group.startswith("N"):
        return (np.nan, np.nan, np.nan)
    parts = group.split(",")
    x = float(parts[0])
    y = float(parts[1])
    s = np.nan if len(parts) < 3 or parts[2].startswith("N") else float(parts[2])
    return (x, y, s)


def read_window(path, lo, hi):
    players, pspd, ball, bspd = [], [], [], []
    with open(path) as handle:
        for line in handle:
            fid_text, player_text, ball_text = line.strip().split(":")
            fid = int(fid_text)
            if fid < lo:
                continue
            if fid > hi:
                break
            xy, sd = [], []
            for group in player_text.split(";"):
                x, y, s = parse_group(group)
                xy.append((x * PL, y * PW))
                sd.append(s)
            players.append(xy)
            pspd.append(sd)
            x, y, s = parse_group(ball_text)
            ball.append((x * PL, y * PW))
            bspd.append(s)
    return (
        np.asarray(players, dtype=np.float32),
        np.asarray(pspd, dtype=np.float32),
        np.asarray(ball, dtype=np.float32),
        np.asarray(bspd, dtype=np.float32),
    )


def finite_stats(values, mask):
    """Mean/percentiles over the finite values inside a mask (inf and NaN are excluded)."""
    selected = values[mask]
    selected = selected[np.isfinite(selected)]
    if selected.size == 0:
        return (np.nan,) * 5
    return (
        float(selected.mean()),
        float(np.percentile(selected, 25)),
        float(np.percentile(selected, 50)),
        float(np.percentile(selected, 75)),
        float(selected.max()),
    )


def main():
    gt = pd.read_csv(GT)["label"].values
    lo, hi = WINDOW
    players, player_speed, ball, ball_speed = read_window(ATD, lo + 1, hi)

    alive = np.isin(gt[lo:hi], ["H", "A"])
    dead = gt[lo:hi] == "D"

    diff = ball[:, None, :] - players
    distance = np.sqrt((diff ** 2).sum(axis=2))
    distance[~np.isfinite(distance)] = np.inf
    nearest = distance.min(axis=1)

    within1 = (distance < 1.0).sum(axis=1)
    within2 = (distance < 2.0).sum(axis=1)
    within3 = (distance < 3.0).sum(axis=1)

    # Ball movement between consecutive frames. A jump larger than 8 m means the ball was
    # re-acquired somewhere else, not that it travelled: tracking re-acquisition is a jump.
    step = np.full(len(ball), np.nan)
    step[1:] = np.sqrt(((ball[1:] - ball[:-1]) ** 2).sum(axis=1))
    moving_ball = np.isfinite(step) & (step > 0.05) & (step < 8.0)

    present = np.isfinite(ball[:, 0])
    speed_known = np.isfinite(ball_speed)

    print("window {}..{}  ({} frames)".format(lo, hi, hi - lo))
    print("truth: H={} A={} D={}".format(
        int((gt[lo:hi] == "H").sum()), int((gt[lo:hi] == "A").sum()), int(dead.sum())))
    print()
    print("{:<38} {:>12} {:>12}".format("feature", "GT alive", "GT dead"))

    def line(name, a, b):
        print("{:<38} {:>12.3f} {:>12.3f}".format(name, a, b))

    line("ball present", float(present[alive].mean()), float(present[dead].mean()))
    line("ball speed field known", float(speed_known[alive].mean()), float(speed_known[dead].mean()))
    line("ball moved this frame (alive ball)", float(moving_ball[alive].mean()), float(moving_ball[dead].mean()))
    line("players within 1m of ball", float(within1[alive].mean()), float(within1[dead].mean()))
    line("players within 2m of ball", float(within2[alive].mean()), float(within2[dead].mean()))
    line("players within 3m of ball", float(within3[alive].mean()), float(within3[dead].mean()))
    line("NO player within 2m of ball", float((within2[alive] == 0).mean()), float((within2[dead] == 0).mean()))
    line("NO player within 3m of ball", float((within3[alive] == 0).mean()), float((within3[dead] == 0).mean()))
    for index, name in enumerate(("nearest player mean", "p25", "p50", "p75", "max")):
        a = finite_stats(nearest, alive)[index]
        b = finite_stats(nearest, dead)[index]
        line("nearest player (m) " + name, a, b)
    line("players tracked (mean)", float(np.isfinite(players[:, :, 0]).sum(axis=1)[alive].mean()),
         float(np.isfinite(players[:, :, 0]).sum(axis=1)[dead].mean()))
    speeds = np.where(np.isfinite(player_speed), player_speed, np.nan)
    with np.errstate(invalid="ignore"):
        activity = np.nanmean(speeds, axis=1)
    line("mean player speed (m/s)", float(np.nanmean(activity[alive])), float(np.nanmean(activity[dead])))
    moving = (np.isfinite(player_speed) & (player_speed > 2.0)).sum(axis=1)
    line("players moving >2m/s", float(moving[alive].mean()), float(moving[dead].mean()))
    line("NO player moving >2m/s", float((moving[alive] == 0).mean()), float((moving[dead] == 0).mean()))

    # ---- geometry at a genuine change of possession ------------------------------------------------
    labels = gt[lo:hi]
    changes = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    real_changes = [
        index
        for index in changes
        if labels[index] != "D" and labels[index - 1] != "D" and labels[index] != labels[index - 1]
    ]
    print("\n{} genuine possession changes in the window".format(len(real_changes)))
    print("what the geometry looks like AT the change, and just BEFORE it:")
    for tag, offset in (("at change", 0), ("1s before", -25), ("2s before", -50)):
        d_home, d_away, gap, new_dist, old_dist = [], [], [], [], []
        for index in real_changes:
            frame = index + offset
            if frame < 0:
                continue
            new_team = labels[index]
            new_dist.append(nearest[frame])
            old_dist.append(np.inf)
            d_home.append(np.nan)
            d_away.append(np.nan)
            gap.append(np.nan)
        # recompute the two team distances properly
        home_mask = np.arange(players.shape[1]) < 24
        away_mask = ~home_mask
        dh = np.where(np.isfinite(distance[:, home_mask]), distance[:, home_mask], np.inf).min(axis=1)
        da = np.where(np.isfinite(distance[:, away_mask]), distance[:, away_mask], np.inf).min(axis=1)
        for index in real_changes:
            frame = index + offset
            if frame < 0:
                continue
            new_team = labels[index]
            new_d = dh[frame] if new_team == "H" else da[frame]
            old_d = da[frame] if new_team == "H" else dh[frame]
            new_dist.append(new_d)
            old_dist.append(old_d)
            gap.append(old_d - new_d)
        print("  {:<10} new-owner distance: mean {:.2f} median {:.2f} | old-owner distance: mean "
              "{:.2f} median {:.2f} | gap (old-new): mean {:+.2f} median {:+.2f}".format(
                  tag,
                  np.nanmean(new_dist[1:]), np.nanmedian(new_dist[1:]),
                  np.nanmean(old_dist[1:]), np.nanmedian(old_dist[1:]),
                  np.nanmean(gap[1:]), np.nanmedian(gap[1:])))

    # ---- Smart Tagging set pieces against the truth -----------------------------------------------
    root = ET.parse(SMART).getroot()
    pieces = []
    for instance in root.iter("instance"):
        if instance.findtext("code") != "SET PIECES":
            continue
        start = int(round(float(instance.findtext("start")) * 25))
        end = int(round(float(instance.findtext("end")) * 25))
        kind = ""
        for label in instance.findall("label"):
            if label.findtext("group") == "Type":
                kind = label.findtext("text")
        pieces.append((start, end, kind))
    pieces.sort()

    print("\nSET PIECES windows vs the truth's D label (whole match summary):")
    for start, end, kind in pieces:
        if end <= lo or start >= hi:
            continue
        segment = gt[start:end]
        print("  {:7d}-{:7d} {:20s} truth D {:5.1%}  length {:5.1f}s".format(
            start, end, kind, float((segment == "D").mean()), (end - start) / 25.0))


if __name__ == "__main__":
    sys.exit(main())
