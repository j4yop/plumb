"""Choose the merge length without any labels, by asking which one the geometry supports.

Why this exists
---------------
The organisers' clarification email draws three lines:

    allowed   "Running automatic checks using only the provided data."
    allowed   "Using as input the video, the automatic tracking data, the smart tagging or any
               other generated data, as long as your algorithm was not trained on the ground
               truth or on the provided video."
    forbidden "Training, fitting or calibrating your algorithm on the ground-truth possession data
               or on the provided video."

So the *tracking* may be used to choose a parameter; the *possession labels* and the *video* may
not. That gives a third route for the one parameter the two references disagree about — how long
a team must hold the ball before it counts as a possession — and it needs no labels at all:

    **perturbation stability.** Hide some of the ball observations, recompute the possession
    sequence, and ask how much of it changed. A merge length that is genuinely supported by the
    geometry produces the same answer whether you can see the ball or not; a merge length that is
    fitting noise produces a different answer every time the tracker blinks.

The criterion is computed on the provided tracking and, independently, on **all three** external
sample matches. Where they agree, the value is not a fit to anything.
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mtah.config import Config
from mtah.pipeline import decide
from mtah.match import Match

MERGE_LENGTHS = (6, 12, 25, 50, 100)
HIDE_FRACTION = 0.2
TRIALS = 5


def possession_sequence(match: Match, config: Config, hide: np.ndarray = None) -> np.ndarray:
    """The possession label per frame, with some ball observations hidden."""
    if hide is not None:
        import copy

        copy_match = copy.copy(match)
        ball_xy = match.ball_xy.copy()
        ball_xy[hide] = np.nan
        copy_match.ball_xy = ball_xy
        match = copy_match
    evidence, decision = decide(match, config)
    return decision.labels


def _spells(labels: np.ndarray) -> List[Tuple[int, int, int]]:
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [labels.size]))
    return [(int(a), int(b), int(labels[a])) for a, b in zip(starts, stops)]


def _survival(baseline: np.ndarray, perturbed: np.ndarray, iou: float = 0.7) -> float:
    """The share of baseline possessions that still exist in the perturbed run.

    Frame-level agreement is dominated by the long possessions and barely moves with the merge
    length. The metric matches *intervals*, so the criterion has to be about intervals: a
    possession survives if some possession in the perturbed run overlaps it by at least the IoU
    the metric's headline threshold uses.
    """
    base = [(a, b) for a, b, label in _spells(baseline) if label in (0, 1)]
    other = [(a, b) for a, b, label in _spells(perturbed) if label in (0, 1)]
    if not base:
        return 0.0
    survived = 0
    for a, b in base:
        best = 0.0
        for c, d in other:
            intersection = min(b, d) - max(a, c)
            union = max(b, d) - min(a, c)
            if intersection > 0 and union > 0:
                best = max(best, intersection / union)
        if best >= iou:
            survived += 1
    return survived / len(base)


def stability(match: Match, config: Config, seed: int = 0) -> Tuple[float, float]:
    """How much of the possession structure survives the ball blinking.

    Returns (share of possessions that survive, mean number of possessions).
    """
    baseline = possession_sequence(match, config)
    rng = np.random.RandomState(seed)
    survivals: List[float] = []
    counts: List[float] = []
    observed = np.isfinite(match.ball_xy[:, 0])

    for _ in range(TRIALS):
        hide = observed & (rng.rand(match.n_frames) < HIDE_FRACTION)
        perturbed = possession_sequence(match, config, hide=hide)
        survivals.append(_survival(baseline, perturbed))
        counts.append(float(np.sum((perturbed[:-1] != perturbed[1:]) & (perturbed[1:] != 2))))

    return float(np.mean(survivals)), float(np.mean(counts))


def sweep(match: Match, label: str) -> None:
    print("\n{}: {} frames".format(label, match.n_frames))
    print("  {:<12} {:>16} {:>14} {:>14}".format(
        "merge (frames)", "spell survival", "spell changes", "possessions"))
    for length in MERGE_LENGTHS:
        config = Config(**{**Config().as_dict(), "min_control_frames": length})
        agreement, changes = stability(match, config)
        labels = possession_sequence(match, config)
        possessions = int(np.sum((labels[:-1] != labels[1:]) & (labels[1:] != 2)))
        print("  {:<12} {:>15.1%} {:>14.0f} {:>14}".format(
            str(length), agreement, changes, possessions))


def main() -> int:
    import sys as _sys

    _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    try:
        import external_tuning as et
    except ImportError:
        et = None

    from mtah.match import load_match

    config = Config()
    data_dir = os.environ.get("MTAH_DATA_DIR", "data")
    try:
        match = load_match(Config(data_dir=data_dir))
    except FileNotFoundError:
        print("the provided match is not on this machine; running the external games only")
    else:
        sweep(match, "provided match (tracking only, no labels, no video)")

    if et is not None and os.path.isdir(et.SAMPLE_ROOT):
        for game in (1, 2, 3):
            try:
                external_match, _truth, _config = et.load_game(game, config)
            except FileNotFoundError:
                continue
            sweep(external_match, "external game {} (tracking only, no labels, no video)".format(game))
    return 0


if __name__ == "__main__":
    sys.exit(main())
