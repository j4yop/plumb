"""Shared fixtures for the test suite: tiny synthetic matches, evidence and configurations.

Everything in this suite is hermetic. No test reads the licensed match data under ``data/``,
no test opens a socket, and no test needs more than numpy and pytest. Every object is
built by hand out of arrays a few hundred bytes long.

The one thing that *is* real is the vocabulary: the same phase codes, the same label codes
and the same metric units (metres and seconds) that the pipeline uses.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

# Make the package importable even when the suite is run without `pip install -e .`.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from mtah.config import BALL_OBSERVED, FIRST_HALF, Config  # noqa: E402
from mtah.evidence import Evidence  # noqa: E402
from mtah.match import Match  # noqa: E402


# --------------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def config() -> Config:
    """A configuration whose *graded* window starts at frame 0.

    The published boundaries put the first half at frames 11185..90651, so a test that used
    the real configuration would find none of its synthetic frames graded, and every frame
    would come out as "outside the match". This one shifts the published structure so that
    frames 0..N-1 are first-half (graded, not warm-up) frames. Nothing else changes: the
    radii, the margins and the spell lengths are the shipped ones.
    """
    return Config(
        pre_match_frames=(-100, -1),
        first_half_frames=(0, 100_000),
        half_time_frames=(100_001, 200_000),
        second_half_frames=(200_001, 300_000),
        second_half_kickoff_frame=200_003,
        post_match_frames=(300_001, 400_000),
    )


# --------------------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------------------

# The dtype each field of ``Evidence`` is expected to have.
_EVIDENCE_DTYPES = {
    "ball_present": bool,
    "ball_speed": np.float32,
    "ball_out_of_play": bool,
    "d_home": np.float32,
    "d_away": np.float32,
    "players_home": np.int16,
    "players_away": np.int16,
    "activity": np.float32,
    "moving_players": np.int16,
    "phase": np.int8,
    "graded": bool,
    "warmup": bool,
    "absence_class": np.int8,
    "dead": bool,
    "set_piece": bool,
}


def _broadcast(value, n_frames: int, dtype):
    """Turn a scalar or a per-frame sequence into an array of length ``n_frames``."""
    if isinstance(value, (list, tuple)):
        value = np.asarray(value)
    if np.isscalar(value):
        array = np.full(n_frames, value)
    else:
        array = np.asarray(value)
        if array.shape != (n_frames,):
            raise ValueError(
                "expected a scalar or {} values, got {}".format(n_frames, array.shape)
            )
    return array.astype(dtype, copy=False)


@pytest.fixture
def evidence_factory():
    """Build an :class:`Evidence` by hand.

    Every field defaults to a boring, plausible value: the ball is tracked, the home team
    is 20 m from the ball and the away team 1 m from it, the match is graded and running,
    nothing is dead. Pass ``n_frames`` and then override any field with a scalar (broadcast
    over every frame) or a per-frame sequence.
    """

    def build(n_frames: int, **overrides) -> Evidence:
        fields = {
            "ball_present": True,
            "ball_speed": 0.0,
            "ball_out_of_play": False,
            "d_home": 1.0,
            "d_away": 20.0,
            "players_home": 11,
            "players_away": 11,
            "activity": 0.0,
            "moving_players": 0,
            "phase": FIRST_HALF,
            "graded": True,
            "warmup": False,
            "absence_class": BALL_OBSERVED,
            "dead": False,
            "set_piece": False,
        }
        unknown = set(overrides) - set(fields)
        if unknown:
            raise ValueError("unknown evidence fields: {}".format(sorted(unknown)))
        fields.update(overrides)

        arrays = {
            name: _broadcast(value, n_frames, _EVIDENCE_DTYPES[name])
            for name, value in fields.items()
        }

        # ``near_team`` and ``near_dist`` are conclusions: keep them consistent with the
        # distances unless the caller says otherwise.
        d_home = arrays["d_home"]
        d_away = arrays["d_away"]
        near_dist = np.minimum(d_home, d_away)
        near_team = np.where(
            np.isinf(near_dist), -1, np.where(d_home <= d_away, 0, 1)
        ).astype(np.int8)
        arrays["near_dist"] = near_dist
        arrays["near_team"] = near_team

        return Evidence(n_frames=n_frames, **arrays)

    return build


# --------------------------------------------------------------------------------------------------
# Match
# --------------------------------------------------------------------------------------------------


@pytest.fixture
def match_factory():
    """Build a tiny synthetic :class:`Match`: four track slots, two per team."""

    def build(
        n_frames: int,
        *,
        ball_xy=None,
        player_xy=None,
        player_speed=None,
        slot_team=(0, 0, 1, 1),
        set_pieces=(),
    ) -> Match:
        slot_team = np.asarray(slot_team, dtype=np.int8)
        n_slots = int(slot_team.shape[0])

        if player_xy is None:
            player_xy = np.zeros((n_frames, n_slots, 2), dtype=np.float32)
        player_xy = np.asarray(player_xy, dtype=np.float32).reshape(n_frames, n_slots, 2)

        if player_speed is None:
            player_speed = np.zeros((n_frames, n_slots), dtype=np.float32)
        player_speed = np.asarray(player_speed, dtype=np.float32).reshape(n_frames, n_slots)

        if ball_xy is None:
            ball_xy = np.full((n_frames, 2), np.nan, dtype=np.float32)
        ball_xy = np.asarray(ball_xy, dtype=np.float32).reshape(n_frames, 2)

        return Match(
            n_frames=n_frames,
            n_slots=n_slots,
            team_names=("Alpha FC", "Beta United"),
            slot_team=slot_team,
            player_xy=player_xy,
            player_speed=player_speed,
            ball_xy=ball_xy,
            ball_speed=np.full((n_frames,), np.nan, dtype=np.float32),
            set_pieces=list(set_pieces),
        )

    return build
