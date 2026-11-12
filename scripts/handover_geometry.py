"""What does a genuine change of possession look like in the tracking?

The scorer matches possessions, so the *timing* of our hand-overs decides the score. Our first
submission switched roughly five seconds late, because the ball is missing on 41% of frames: a
hand-over that happens while the ball is untracked can only be noticed when the ball reappears.

This script asks, for each genuine change in the public window:

* was the ball visible at the change?
* how far were the two teams' nearest players from the ball (or from its last known position)?
* which team was closest to the last known ball position while the ball was missing?

The last question is the one that matters: if the team that *gains* the ball is the one whose
players converge on the ball's last known position, then a hand-over can be inferred during the
occlusion instead of waiting for the ball to reappear.
"""

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "scripts")
from analyze_window import ATD, GT, WINDOW, read_window  # noqa: E402


def main():
    gt = pd.read_csv(GT)["label"].values
    lo, hi = WINDOW
    truth = gt[lo:hi]
    players, pspd, ball, bspd = read_window(ATD, lo + 1, hi)

    diff = ball[:, None, :] - players
    distance = np.sqrt((diff ** 2).sum(axis=2))
    distance[~np.isfinite(distance)] = np.inf
    home = np.arange(players.shape[1]) < 24
    d_home = np.where(np.isfinite(distance[:, home]), distance[:, home], np.inf).min(axis=1)
    d_away = np.where(np.isfinite(distance[:, ~home]), distance[:, ~home], np.inf).min(axis=1)
    present = np.isfinite(ball[:, 0])

    # Distance from every player to the *last known* ball position, tracked forward.
    last_x = np.full(len(ball), np.nan)
    last_y = np.full(len(ball), np.nan)
    current_x = current_y = np.nan
    for index in range(len(ball)):
        if present[index]:
            current_x, current_y = ball[index]
        last_x[index] = current_x
        last_y[index] = current_y
    to_last = np.sqrt((players[:, :, 0] - last_x[:, None]) ** 2 + (players[:, :, 1] - last_y[:, None]) ** 2)
    to_last[~np.isfinite(to_last)] = np.inf
    l_home = np.where(np.isfinite(to_last[:, home]), to_last[:, home], np.inf).min(axis=1)
    l_away = np.where(np.isfinite(to_last[:, ~home]), to_last[:, ~home], np.inf).min(axis=1)

    changes = np.flatnonzero(truth[1:] != truth[:-1]) + 1
    real = [
        index
        for index in changes
        if truth[index] != "D" and truth[index - 1] != "D" and truth[index] != truth[index - 1]
    ]

    print("{} genuine changes in the window".format(len(real)))
    header = "{:<5} {:<7} {:>6} {:>6} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
        "frame", "to", "ball", "gap", "d_new", "d_old", "last_new", "last_old", "gapL"
    )
    print(header)
    for index in real:
        new_team = truth[index]
        new_d = d_home[index] if new_team == "H" else d_away[index]
        old_d = d_away[index] if new_team == "H" else d_home[index]
        new_l = l_home[index] if new_team == "H" else l_away[index]
        old_l = l_away[index] if new_team == "H" else l_home[index]
        print(
            "{:<5} {:<7} {:>6} {:>6} {:>8.2f} {:>8.2f} {:>8.2f} {:>8.2f} {:>8.2f}".format(
                index,
                new_team,
                "yes" if present[index] else "NO",
                "",
                new_d,
                old_d,
                new_l,
                old_l,
                old_l - new_l,
            )
        )

    # Does the *gaining* team converge on the last known ball position before the ball reappears?
    print("\nFor each change: how the 'closest to the last known ball position' gap evolves")
    print("{:<6} {:>8} {:>8} {:>8} {:>8} {:>8}".format("frame", "-50f", "-25f", "-5f", "+5f", "+25f"))
    for index in real:
        row = []
        for offset in (-50, -25, -5, 5, 25):
            frame = index + offset
            if frame < 0 or frame >= len(l_home):
                row.append(np.nan)
                continue
            gap = l_away[frame] - l_home[frame] if truth[index] == "H" else l_home[frame] - l_away[frame]
            row.append(gap)
        print("{:<6} {:>8.2f} {:>8.2f} {:>8.2f} {:>8.2f} {:>8.2f}".format(index, *row))

    # How often is the ball visible at all between a change and the next?
    gaps = np.diff(real)
    visible = []
    for start, end in zip(real, real[1:]):
        visible.append(float(present[start:end].mean()))
    print("\nmean fraction of frames with the ball visible between consecutive changes: {:.2f}".format(
        float(np.mean(visible)) if visible else float("nan")))


if __name__ == "__main__":
    sys.exit(main())
