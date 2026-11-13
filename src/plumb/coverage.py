"""The reliability engine: how much of a claim the tracking can actually carry.

This is the heart of the project. Every number the system states has to answer a question the
raw data cannot: *how much of this rests on the tracker, and where does it stop being true?*

The engine is built from four per-frame observations, all of them automatic checks on the provided
tracking — no labels, no video:

``ball_seen``
    the ball is observed at all.
``ball_stable``
    it did not jump: a re-acquisition is a discontinuity of several metres, and a claim that
    depends on the ball's exact position is weaker there.
``no_duplicates``
    no two players of the same team are within 1.5 m of each other, which is the signature of the
    tracker counting one player twice.
``full_pitch``
    at least eighteen players are visible, which is what a real match looks like.

Their product is a **support score** per frame, and the coverage of any claim is the support over
exactly the frames that claim depends on — not over the match. A claim about the final third is
only as good as the final third.

The engine also computes the two things that turn a number into an honest one:

* the **decision margin**, |d_home − d_away|, which says how close the nearest-player call was;
* the **sensitivity**, the share of frames whose margin is smaller than a given tracking error.
  If a fifth of the frames in a claim were decided by a margin of half a metre, then half a metre
  of tracking error moves the answer, and that is a statement about the claim rather than a
  caveat attached to it.

Nothing here is fitted. The thresholds are physical: a re-acquisition is a jump of more than
three metres, two players of one team inside a metre and a half are the same player counted
twice, and a real match has twenty-two players on the pitch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

# A re-acquisition shows up as a discontinuity; three metres in a frame is not football.
BALL_JUMP_METRES = 3.0
# Two players of one team this close are the same player counted twice.
DUPLICATE_METRES = 1.5
# A full pitch: twenty-two players, minus a couple off the camera.
FULL_PITCH_PLAYERS = 18
# Frames processed at a time, so the pairwise tensors stay small.
CHUNK = 20000


@dataclass
class Coverage:
    """Per-frame quality of the tracking, and the geometry of the decisions taken on it."""

    ball_seen: np.ndarray
    ball_stable: np.ndarray
    no_duplicates: np.ndarray
    full_pitch: np.ndarray
    support: np.ndarray  # composite, 0..1
    decision_margin: np.ndarray  # |d_home - d_away|, inf where neither is near
    duplicate_players: np.ndarray
    players_visible: np.ndarray

    # -- slicing ---------------------------------------------------------------------------------

    def scope(self, frames: Optional[np.ndarray] = None) -> Dict[str, float]:
        """The coverage of a set of frames: what a claim resting on them can lean on.

        This is the whole point. A claim about the final third is not covered by the match's
        coverage; it is covered by the final third's coverage, and the two can be very
        different.
        """
        if frames is None:
            frames = np.ones(self.support.shape[0], dtype=bool)
        frames = np.asarray(frames, dtype=bool)
        count = int(frames.sum())
        if count == 0:
            return {
                "frames": 0,
                "ball_visibility": 0.0,
                "support": 0.0,
                "duplicate_share": 0.0,
                "mean_players": 0.0,
            }
        return {
            "frames": count,
            "ball_visibility": float(self.ball_seen[frames].mean()),
            "support": float(self.support[frames].mean()),
            "duplicate_share": float((self.duplicate_players[frames] > 0).mean()),
            "mean_players": float(self.players_visible[frames].mean()),
        }

    def sensitivity(self, frames: Optional[np.ndarray] = None, sigma: float = 0.5) -> float:
        """The share of frames decided by a margin thinner than ``sigma`` metres.

        This is the honest error bar: a position error of ``sigma`` could flip the call on any
        frame whose two candidates were that close, so the claim's answer could move by roughly
        this much.
        """
        if frames is None:
            frames = np.ones(self.support.shape[0], dtype=bool)
        frames = np.asarray(frames, dtype=bool)
        alive = frames & np.isfinite(self.decision_margin)
        if not alive.any():
            return 0.0
        return float((self.decision_margin[alive] < sigma).mean())

    def jitter(self, frames: Optional[np.ndarray] = None, sigma: float = 0.5) -> float:
        """The widest band the answer could take if the tracking were off by ``sigma`` metres.

        Unlike :meth:`sensitivity`, which counts *frames*, this is a number the same shape as the
        claim: the share of the scoped frames whose ownership could flip.
        """
        return self.sensitivity(frames, sigma)


def build_coverage(analysis) -> Coverage:
    """Compute the per-frame quality of the tracking."""
    match_ball = analysis.ball_xy
    n = analysis.n_frames
    slots = analysis.player_xy.shape[1]

    ball_seen = analysis.evidence.ball_present

    # How far the ball moved between frames. A jump means the tracker re-acquired it elsewhere.
    displacement = np.full(n, np.nan, dtype=np.float32)
    if n > 1:
        delta = match_ball[1:] - match_ball[:-1]
        displacement[1:] = np.sqrt((delta ** 2).sum(axis=1))
    ball_stable = ball_seen.copy()
    jumped = np.isfinite(displacement) & (displacement > BALL_JUMP_METRES)
    ball_stable[jumped] = False

    players_visible = (analysis.evidence.players_home + analysis.evidence.players_away).astype(np.float32)
    duplicate_players = np.zeros(n, dtype=np.int16)

    # The distance matrix is needed for the duplicate test and the decision margin.
    difference = match_ball[:, None, :] - analysis.player_xy
    distance = np.sqrt((difference ** 2).sum(axis=2)).astype(np.float32)
    distance[~np.isfinite(distance)] = np.inf
    del difference

    for team in (0, 1):
        team_slots = np.flatnonzero((analysis.teams == team).any(axis=0))
        if team_slots.size < 2:
            continue
        # Pairwise distances between the players of one team, in chunks: the full tensor would
        # be 800 MB for a match.
        for lo in range(0, n, CHUNK):
            hi = min(n, lo + CHUNK)
            positions = analysis.player_xy[lo:hi, team_slots, :]
            offset = positions[:, :, None, :] - positions[:, None, :, :]
            pair_distance = np.sqrt((offset ** 2).sum(axis=3)).astype(np.float32)
            too_close = (pair_distance < DUPLICATE_METRES) & (pair_distance > 0)
            diagonal = np.arange(too_close.shape[1])
            too_close[:, diagonal, diagonal] = False
            # Each close pair is counted twice.
            duplicate_players[lo:hi] += (too_close.sum(axis=(1, 2)) // 2).astype(np.int16)
    no_duplicates = duplicate_players == 0

    full_pitch = players_visible >= FULL_PITCH_PLAYERS

    support = (
        ball_seen.astype(np.float32)
        + ball_stable.astype(np.float32)
        + no_duplicates.astype(np.float32)
        + full_pitch.astype(np.float32)
    ) / 4.0

    with np.errstate(invalid="ignore"):
        margin = np.abs(analysis.evidence.d_home - analysis.evidence.d_away).astype(np.float32)
    margin[~np.isfinite(margin)] = np.inf

    return Coverage(
        ball_seen=ball_seen,
        ball_stable=ball_stable,
        no_duplicates=no_duplicates,
        full_pitch=full_pitch,
        support=support,
        decision_margin=margin,
        duplicate_players=duplicate_players,
        players_visible=players_visible,
    )


def zone_mask(
    ball_xy: np.ndarray,
    attacking_right: np.ndarray,
    zone: str,
    length_m: float,
    width_m: float,
) -> np.ndarray:
    """Frames whose ball is in a named zone, relative to the team in possession.

    Zones are relative to a team's own attacking direction, so "the final third" means the third
    the team is attacking into.
    """
    if zone in ("all", "", None):
        return np.ones(ball_xy.shape[0], dtype=bool)

    x = ball_xy[:, 0]
    y = ball_xy[:, 1]
    # Progress from the point of view of the team in possession.
    progress = np.where(attacking_right, x, length_m - x)

    inside_width = (y >= width_m / 3) & (y <= 2 * width_m / 3)

    if zone == "defensive-third":
        return progress < length_m / 3
    if zone == "middle-third":
        return (progress >= length_m / 3) & (progress <= 2 * length_m / 3)
    if zone == "attacking-third":
        return progress > 2 * length_m / 3
    if zone == "left-channel":
        return inside_width & (y < width_m / 2)
    if zone == "right-channel":
        return inside_width & (y > width_m / 2)
    if zone == "centre":
        return inside_width & (y > width_m / 3) & (y < 2 * width_m / 3)
    if zone == "box":
        return (progress > length_m - 16.5) & (np.abs(y - width_m / 2) < 20.3)
    raise ValueError("unknown zone: {}".format(zone))


ZONES = (
    "defensive-third",
    "middle-third",
    "attacking-third",
    "left-channel",
    "right-channel",
    "centre",
    "box",
)
