"""Decide which team each track slot belongs to, in every frame.

Why this module exists
----------------------
The metadata assigns every track slot to a team, and the organisers warn that slots "appear,
vanish and swap identity as the tracker loses and re-acquires people". A slot that has swapped
carries the wrong team label from that moment on. That is not a hypothetical: the slot that is
most often the nearest player to the ball in the opening minutes contradicts the organisers' own
labels for a large part of the match, and it is exactly the slot that decides the kickoff
possession.

The fix uses no labels at all: **a player is on the team its neighbours are on.** Each slot is
assigned, frame by frame, by the majority vote of its *k* nearest spatial neighbours, using the
metadata assignment only as the starting point. A slot that has swapped identity is surrounded
by its new team-mates, so the vote follows it; a slot that has merely strayed near the opponent
is still surrounded by its own team, so the vote keeps it where it belongs.

The interface is one function and one array: :func:`assign_teams` returns, for every frame and
every slot, the team it belongs to.
"""

from __future__ import annotations

import numpy as np

HOME, AWAY = 0, 1


def assign_teams(
    player_xy: np.ndarray,
    slot_team: np.ndarray,
    k: int = 5,
    chunk_frames: int = 4000,
    iterations: int = 2,
) -> np.ndarray:
    """Per-frame team membership for every slot.

    Parameters
    ----------
    player_xy:
        ``(n_frames, n_slots, 2)`` positions in metres, NaN where unobserved.
    slot_team:
        ``(n_slots,)`` starting team per slot, from the metadata.
    k:
        How many nearest neighbours vote.
    iterations:
        How many times the neighbour vote is recomputed using the previous result as the seed.
        Two passes are enough for a swap to propagate.

    Returns
    -------
    ``(n_frames, n_slots)`` int8 array: 0 for home, 1 for away.
    """
    n_frames, n_slots = player_xy.shape[0], player_xy.shape[1]
    current = np.tile(np.asarray(slot_team, dtype=np.int8), (n_frames, 1))
    k = max(1, min(k, n_slots - 1))
    index = np.arange(n_slots)

    for _ in range(max(1, iterations)):
        current = _vote_chunked(player_xy, current, k, chunk_frames)
    return current


def _vote_chunked(
    player_xy: np.ndarray, seed: np.ndarray, k: int, chunk_frames: int
) -> np.ndarray:
    """One pass of neighbour voting, in chunks so the distance tensor stays small."""
    n_frames, n_slots = player_xy.shape[0], player_xy.shape[1]
    out = np.empty_like(seed)

    for start in range(0, n_frames, chunk_frames):
        stop = min(start + chunk_frames, n_frames)
        block = player_xy[start:stop]
        size = stop - start

        dx = block[:, :, None, 0] - block[:, None, :, 0]
        dy = block[:, :, None, 1] - block[:, None, :, 1]
        distance = dx * dx + dy * dy
        # A slot is not its own neighbour.
        rows = np.arange(size)
        distance[rows[:, None], np.arange(n_slots)[None, :], np.arange(n_slots)[None, :]] = np.inf
        # Unobserved slots are nowhere; they must not vote.
        distance[~np.isfinite(block[:, :, 0])] = np.inf

        nearest = np.argpartition(distance, k, axis=2)[:, :, :k]
        seed_block = seed[start:stop]
        expanded = np.broadcast_to(seed_block[:, None, :], (size, n_slots, n_slots))
        votes = np.take_along_axis(expanded, nearest, axis=2)
        home_votes = (votes == HOME).sum(axis=2)
        away_votes = (votes == AWAY).sum(axis=2)
        # Ties go to the slot's current team: no evidence, no change.
        ties = home_votes == away_votes
        decided = np.where(home_votes > away_votes, HOME, AWAY)
        out[start:stop] = np.where(ties, seed_block, decided)
        # A slot that is not observed this frame has no evidence at all: it keeps its team.
        out[start:stop] = np.where(np.isfinite(block[:, :, 0]), out[start:stop], seed_block)

    return out
