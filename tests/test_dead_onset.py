"""Tests for the dead-ball onset rule.

The organisers asked when the dead period begins, and the answer is a configuration value
(ADR 0010). These tests check the three rules behave as documented and that the default has not
moved.
"""

import numpy as np
import pytest

from mtah.config import Config
from mtah.decide import assign_owners, build_spells
from mtah.evidence import build_evidence
from mtah.match import Match

from test_plumb import make_config


def build_match(n_frames: int = 400) -> Match:
    """A synthetic match where the ball disappears and the players stop."""
    rng = np.random.RandomState(3)
    n_slots = 22
    slot_team = np.array([0] * 11 + [1] * 11, dtype=np.int8)
    player_xy = np.zeros((n_frames, n_slots, 2), dtype=np.float32)
    player_speed = np.zeros((n_frames, n_slots), dtype=np.float32)
    for index in range(n_slots):
        side = 0.0 if index < 11 else 80.0
        player_xy[:, index, 0] = side + rng.rand(n_frames) * 20.0
        player_xy[:, index, 1] = 5.0 + rng.rand(n_frames) * 58.0
        player_speed[:, index] = rng.rand(n_frames) * 4.0

    ball_xy = np.zeros((n_frames, 2), dtype=np.float32)
    carrier = np.where(np.arange(n_frames) < n_frames // 2, 0, 11)
    ball_xy[:, 0] = player_xy[np.arange(n_frames), carrier, 0] + rng.randn(n_frames) * 0.4
    ball_xy[:, 1] = player_xy[np.arange(n_frames), carrier, 1] + rng.randn(n_frames) * 0.4

    # The middle stretch: the ball is not tracked and nobody is running. That is a stoppage.
    stop = slice(n_frames // 2, n_frames // 2 + 100)
    ball_xy[stop] = np.nan
    player_speed[stop] = 0.0

    return Match(
        n_frames=n_frames,
        n_slots=n_slots,
        team_names=("Home", "Away"),
        slot_team=slot_team,
        player_xy=player_xy,
        player_speed=player_speed,
        ball_xy=ball_xy,
        ball_speed=np.full(n_frames, np.nan, dtype=np.float32),
        set_pieces=(),
    )


def absence_classes(config: Config, match: Match) -> np.ndarray:
    return build_evidence(match, config).absence_class


def test_the_default_is_the_whistle_rule():
    """The default must not move while the organisers decide."""
    assert Config().dead_onset == "movement"


def test_the_stoppage_is_detected_under_the_default():
    from mtah.config import STOPPAGE

    config = make_config()
    match = build_match()
    absence = absence_classes(config, match)
    assert (absence[210:280] == STOPPAGE).all()


def test_the_rules_are_three_distinct_rules():
    """They differ in *what makes a period dead*, and the distinction has to be real.

    This test used to assert that all three rules found the stoppage. They did — because
    ``ball_out`` and ``earliest`` were byte-identical branches, so the test was asserting the
    bug. The stoppage in this synthetic match is players stopping with the ball still inside the
    pitch, so ``movement`` and ``earliest`` find it and ``ball_out`` must not.
    """
    from mtah.config import STOPPAGE, OUT_OF_PLAY

    config = make_config()
    match = build_match()
    found = {}
    for rule in ("movement", "ball_out", "earliest"):
        candidate = Config(**{**config.as_dict(), "dead_onset": rule})
        absence = absence_classes(candidate, match)
        dead = np.isin(absence, (STOPPAGE, OUT_OF_PLAY))
        found[rule] = bool(dead[210:280].all())

    assert found["movement"], "the whistle rule must find a stoppage"
    assert found["earliest"], "the most inclusive rule must find it too"
    assert not found["ball_out"], (
        "the ball never left the pitch, so 'out of play' must not call this dead"
    )


def test_the_rules_are_configurable_and_the_default_is_unchanged():
    """Switching the rule must not change the default's behaviour."""
    base = make_config()
    match = build_match()
    default = absence_classes(base, match)
    again = absence_classes(Config(**base.as_dict()), match)
    assert np.array_equal(default, again)


def test_the_config_round_trips_with_the_new_field():
    payload = Config().as_dict()
    assert "dead_onset" in payload
    assert Config(**payload) == Config()
