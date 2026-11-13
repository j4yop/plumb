"""The published match structure, and the promise that a configuration is reproducible.

The boundaries in :mod:`mtah.config` are *inputs* published by the organisers, not assumptions
made by this pipeline. If they move, the whole submission moves with them, so they are worth
pinning down in a test rather than in a comment.
"""

import dataclasses

import pytest

from mtah.config import (
    AWAY,
    DEAD,
    FIRST_HALF,
    HALF_TIME,
    HOME,
    LABEL_NAMES,
    PHASE_NAMES,
    POST_MATCH,
    PRE_MATCH,
    SECOND_HALF,
    Config,
    DEFAULT,
)


# --------------------------------------------------------------------------------------------------
# The published boundaries
# --------------------------------------------------------------------------------------------------


def test_the_published_boundaries_are_the_ones_we_ship():
    assert DEFAULT.pre_match_frames == (0, 11184)
    assert DEFAULT.first_half_frames == (11185, 90651)
    assert DEFAULT.half_time_frames == (90652, 110807)
    assert DEFAULT.second_half_frames == (110808, 190197)
    assert DEFAULT.post_match_frames == (190198, 199318)
    assert DEFAULT.second_half_kickoff_frame == 113742


def test_the_match_is_199_319_frames_long():
    """199,319 frames of tactical video at 25 fps: the row count of the submission."""
    assert DEFAULT.post_match_frames[1] + 1 == 199_319


def test_the_graded_window_holds_158_857_frames():
    """The organisers score the two halves and nothing else."""
    graded = sum(1 for frame in range(199_319) if DEFAULT.is_graded(frame))
    assert graded == 158_857
    assert graded == (
        DEFAULT.first_half_frames[1]
        - DEFAULT.first_half_frames[0]
        + 1
        + DEFAULT.second_half_frames[1]
        - DEFAULT.second_half_frames[0]
        + 1
    )


def test_the_warm_up_block_is_2_934_frames():
    """The second half is graded before its kickoff; that stretch is dead ball."""
    assert DEFAULT.second_half_kickoff_frame - DEFAULT.second_half_frames[0] == 2_934


# --------------------------------------------------------------------------------------------------
# phase_of
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "frame,phase",
    [
        (0, PRE_MATCH),
        (11184, PRE_MATCH),
        (11185, FIRST_HALF),
        (90651, FIRST_HALF),
        (90652, HALF_TIME),
        (110807, HALF_TIME),
        (110808, SECOND_HALF),
        (190197, SECOND_HALF),
        (190198, POST_MATCH),
        (199318, POST_MATCH),
    ],
)
def test_phase_of_uses_the_published_boundaries(frame, phase):
    assert DEFAULT.phase_of(frame) == phase


def test_the_phase_codes_have_names():
    assert PHASE_NAMES == ("pre_match", "first_half", "half_time", "second_half", "post_match")
    assert len(PHASE_NAMES) == 5


def test_every_frame_has_a_phase():
    """No frame may fall between two published phases."""
    codes = {DEFAULT.phase_of(frame) for frame in range(0, 199_319, 97)}
    assert codes == {PRE_MATCH, FIRST_HALF, HALF_TIME, SECOND_HALF, POST_MATCH}


# --------------------------------------------------------------------------------------------------
# is_graded / is_warmup
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "frame,graded",
    [
        (0, False),
        (11184, False),
        (11185, True),
        (90651, True),
        (90652, False),
        (110807, False),
        (110808, True),
        (190197, True),
        (190198, False),
        (199318, False),
    ],
)
def test_is_graded_covers_the_two_halves_only(frame, graded):
    assert DEFAULT.is_graded(frame) is graded


@pytest.mark.parametrize(
    "frame,warmup",
    [
        (90651, False),
        (110807, False),
        (110808, True),
        (113741, True),
        (113742, False),
        (190197, False),
    ],
)
def test_is_warmup_is_the_second_half_pre_kickoff_block(frame, warmup):
    assert DEFAULT.is_warmup(frame) is warmup


def test_a_warm_up_frame_is_graded():
    """The warm-up is inside the graded window: it has to be answered, with `D`."""
    assert DEFAULT.is_graded(111_000) is True
    assert DEFAULT.is_warmup(111_000) is True


# --------------------------------------------------------------------------------------------------
# The configuration as a value
# --------------------------------------------------------------------------------------------------


def test_as_dict_round_trips():
    payload = DEFAULT.as_dict()
    assert payload["control_radius_m"] == 2.0
    assert payload["first_half_frames"] == (11185, 90651)

    rebuilt = Config(**payload)
    assert rebuilt == DEFAULT
    assert rebuilt.as_dict() == payload


def test_as_dict_covers_every_field():
    payload = DEFAULT.as_dict()
    assert set(payload) == {field.name for field in dataclasses.fields(Config)}


def test_the_configuration_is_frozen():
    """A run must be reproducible from the configuration that produced it."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.control_radius_m = 3.0


def test_the_thresholds_are_in_football_units():
    """Metres and seconds, never frames (see the module docstring)."""
    assert DEFAULT.control_radius_m == 2.0
    assert DEFAULT.reach_radius_m == 6.0
    assert DEFAULT.handover_margin_m == 0.5
    assert DEFAULT.run_speed_mps == 2.0
    assert DEFAULT.pitch_length_m == 105.3
    assert DEFAULT.pitch_width_m == 68.0
    assert DEFAULT.out_of_play_slack_m == 2.0


def test_the_label_alphabet_is_h_a_d_x():
    assert LABEL_NAMES == ("H", "A", "D", "X")
    assert (HOME, AWAY, DEAD) == (0, 1, 2)
    assert LABEL_NAMES[HOME] == "H"
    assert LABEL_NAMES[AWAY] == "A"
    assert LABEL_NAMES[DEAD] == "D"
