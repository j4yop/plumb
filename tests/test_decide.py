"""Deciding who has the ball, frame by frame, from the evidence.

These are the rules that the public five minutes check, written as the football they
describe: the nearest team has the ball, a contested ball belongs to the last owner, an
untracked ball during live play belongs to the last owner, and a stoppage is dead ball.

The evidence is built by hand so that every test states exactly the situation it is about:
where the ball is, how far the two teams are from it, whether the ball was seen, and
whether the match is running.

The *sizes* in these tests are taken from the configuration rather than written down as
magic numbers: "a control episode too short to be a possession" is expressed as a fraction
of ``min_control_frames``, so the test keeps meaning what it says when the thresholds are
re-tuned.
"""

import numpy as np
import pytest

from mtah.config import AWAY, DEAD, HOME, OCCLUSION, STOPPAGE
from mtah.decide import assign_owners, build_spells
from mtah.evidence import build_evidence


# --------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------


def _sizes(config):
    """Episode, gap and spell lengths derived from the shipped thresholds.

    Returns ``(long_run, short_run, long_gap)``:

    * ``long_run`` is long enough to be both a possession and a spell,
    * ``short_run`` is too short to be controlled possession,
    * ``long_gap`` is longer than a bridged signal gap, so the frames in it are carried
      forward rather than filled in.
    """
    control = config.min_control_frames
    spell = config.min_spell_frames
    long_run = max(control, spell) + 10
    short_run = max(1, control - 10)
    long_gap = max(config.max_signal_gap_frames + 15, spell + 15)
    return long_run, short_run, long_gap


def _distances(n_frames, home=1.0, away=20.0, contested=()):
    """Per-frame distances from the ball to the nearest player of each team.

    ``contested`` lists the frames in which the away team is also inside the control
    radius, which makes the ball contested and nobody's.
    """
    d_home = np.full(n_frames, home, dtype=np.float32)
    d_away = np.full(n_frames, away, dtype=np.float32)
    for frame in contested:
        d_away[frame] = 2.0  # inside the control radius (2.5 m) as well
    return d_home, d_away


def _running_match(match_factory, config, running=True):
    """A match in which the home team holds the ball, the ball disappears for a while
    and then comes back.

    The ball sits at (50, 34) m with a home player half a metre away and the away team ten
    metres away, so the home team is unambiguously in control whenever the ball is tracked.
    """
    long_run, _short_run, long_gap = _sizes(config)
    n_frames = 2 * long_run + long_gap
    head, tail = long_run, long_run

    ball_xy = np.full((n_frames, 2), np.nan, dtype=np.float32)
    ball_xy[:head] = (50.0, 34.0)
    ball_xy[head + long_gap:] = (50.0, 34.0)

    # Eleven players a side, as in a real match: the count of moving players is what
    # separates a stoppage from an occlusion, so it has to be a realistic one.
    n_slots = 22
    player_xy = np.zeros((n_frames, n_slots, 2), dtype=np.float32)
    player_xy[:, 0] = (50.5, 34.0)  # home, 0.5 m from the ball
    player_xy[:, 1] = (48.0, 34.0)  # home, 2.0 m from the ball
    player_xy[:, 2:11] = (30.0, 34.0)  # the rest of the home team
    player_xy[:, 11:] = (60.0, 34.0)  # the away team

    player_speed = np.full((n_frames, n_slots), 5.0, dtype=np.float32)
    if not running:
        player_speed[head:head + long_gap] = 0.0  # nobody is running during the gap

    return match_factory(
        n_frames,
        ball_xy=ball_xy,
        player_xy=player_xy,
        player_speed=player_speed,
        slot_team=np.array([0] * 11 + [1] * 11, dtype=np.int8),
    )


# --------------------------------------------------------------------------------------------------
# Who has the ball
# --------------------------------------------------------------------------------------------------


def test_the_team_nearest_the_ball_gets_the_possession(evidence_factory, config):
    evidence = evidence_factory(40, d_home=1.0, d_away=20.0)
    owners, episodes = assign_owners(evidence, config)

    assert set(owners.tolist()) == {HOME}
    assert episodes == [(0, 40, HOME)]


def test_the_away_team_nearest_the_ball_gets_the_possession(evidence_factory, config):
    evidence = evidence_factory(40, d_home=20.0, d_away=1.0)
    owners, episodes = assign_owners(evidence, config)

    assert set(owners.tolist()) == {AWAY}
    assert episodes == [(0, 40, AWAY)]


def test_a_ball_that_nobody_is_near_is_not_owned(evidence_factory, config):
    """Loose or in flight: the ball is beyond the control radius of everybody."""
    evidence = evidence_factory(40, d_home=12.0, d_away=14.0)
    owners, episodes = assign_owners(evidence, config)

    assert set(owners.tolist()) == {-1}
    assert episodes == []


def test_a_ball_nearer_than_the_handover_margin_is_not_a_hand_over(evidence_factory, config):
    """A pass that travels within a hair of a defender is not a change of possession."""
    evidence = evidence_factory(
        40, d_home=2.0, d_away=2.2
    )  # both inside the radius, and too close to call
    owners, episodes = assign_owners(evidence, config)

    assert set(owners.tolist()) == {-1}
    assert episodes == []


# --------------------------------------------------------------------------------------------------
# The contested ball
# --------------------------------------------------------------------------------------------------


def test_a_contested_ball_keeps_the_previous_owner(evidence_factory, config):
    """Both teams inside the control radius: nobody controls the ball, so the last owner
    keeps it."""
    long_run, _short_run, long_gap = _sizes(config)
    n_frames = 2 * long_run + long_gap
    contested = range(long_run, long_run + long_gap)
    d_home, d_away = _distances(n_frames, contested=contested)
    evidence = evidence_factory(n_frames, d_home=d_home, d_away=d_away)

    owners, episodes = assign_owners(evidence, config)

    middle = long_run + long_gap // 2
    assert owners[long_run - 1] == HOME  # the owner before the contested stretch
    assert owners[middle] == HOME  # contested: the previous owner keeps the ball
    assert owners[long_run + long_gap - 1] == HOME
    assert owners[-1] == HOME

    # The contested stretch is not an episode of its own.
    assert all(team == HOME for _start, _stop, team in episodes)
    assert not any(start <= middle < stop for start, stop, _team in episodes)


def test_a_contested_ball_does_not_hand_the_ball_to_the_away_team(evidence_factory, config):
    long_run, _short_run, long_gap = _sizes(config)
    n_frames = 2 * long_run + long_gap
    d_home, d_away = _distances(n_frames, contested=range(long_run, long_run + long_gap))
    evidence = evidence_factory(n_frames, d_home=d_home, d_away=d_away)
    owners, _episodes = assign_owners(evidence, config)

    assert AWAY not in owners.tolist()


# --------------------------------------------------------------------------------------------------
# The untracked ball
# --------------------------------------------------------------------------------------------------


def test_an_untracked_ball_during_live_play_keeps_the_owner(match_factory, config):
    """The ball goes missing for a while while the players keep running: that is an
    occlusion inside a possession, not a stoppage."""
    long_run, _short_run, long_gap = _sizes(config)
    match = _running_match(match_factory, config, running=True)
    evidence = build_evidence(match, config)

    middle = long_run + long_gap // 2
    assert not evidence.ball_present[middle]
    assert evidence.absence_class[middle] == OCCLUSION
    assert not evidence.dead[middle]

    owners, _episodes = assign_owners(evidence, config)
    assert owners[long_run - 1] == HOME  # the owner before the gap
    assert owners[middle] == HOME  # the owner carries through the occlusion
    assert owners[long_run + long_gap - 1] == HOME
    assert owners[-1] == HOME


def test_an_untracked_ball_with_nobody_running_is_dead(match_factory, config):
    """The ball is missing and almost nobody is moving: a stoppage, so dead ball."""
    long_run, _short_run, long_gap = _sizes(config)
    match = _running_match(match_factory, config, running=False)
    evidence = build_evidence(match, config)

    middle = long_run + long_gap // 2
    assert not evidence.ball_present[middle]
    assert evidence.absence_class[middle] == STOPPAGE
    assert evidence.dead[middle]

    owners, _episodes = assign_owners(evidence, config)
    assert owners[long_run - 1] == HOME  # the ball was alive before the stoppage
    assert owners[middle] == DEAD
    assert owners[long_run + long_gap - 1] == DEAD
    assert owners[-1] == HOME  # the ball is back


def test_a_dead_ball_breaks_the_possession(match_factory, config):
    """A stoppage in the middle of a possession splits it in two."""
    long_run, _short_run, long_gap = _sizes(config)
    match = _running_match(match_factory, config, running=False)
    evidence = build_evidence(match, config)
    owners, _episodes = assign_owners(evidence, config)

    decision = build_spells(owners, evidence, config)
    assert decision.spells == [
        (0, long_run, HOME),
        (long_run, long_run + long_gap, DEAD),
        (long_run + long_gap, 2 * long_run + long_gap, HOME),
    ]


def test_frames_outside_the_graded_window_are_left_alone(evidence_factory, config):
    """Ungraded frames are not scored, so the pipeline does not claim an owner for them."""
    graded = [True] * 20 + [False] * 20
    evidence = evidence_factory(40, d_home=1.0, d_away=20.0, graded=graded)
    owners, _episodes = assign_owners(evidence, config)

    assert set(owners[:20].tolist()) == {HOME}
    assert set(owners[20:].tolist()) == {-1}


# --------------------------------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------------------------------


def test_a_short_control_episode_between_two_episodes_is_absorbed(evidence_factory, config):
    """A brief touch by the away team between two home possessions is a touch, not a change
    of possession: the organisers' definition requires *controlled* possession."""
    long_run, short_run, _long_gap = _sizes(config)
    n_frames = 2 * long_run + short_run

    d_home = np.full(n_frames, 1.0, dtype=np.float32)
    d_away = np.full(n_frames, 10.0, dtype=np.float32)
    d_home[long_run:long_run + short_run] = 10.0
    d_away[long_run:long_run + short_run] = 1.0

    evidence = evidence_factory(n_frames, d_home=d_home, d_away=d_away)
    owners, episodes = assign_owners(evidence, config)

    # No episode of the away team survives the absorption.
    assert all(team == HOME for _start, _stop, team in episodes)
    assert set(owners.tolist()) == {HOME}

    decision = build_spells(owners, evidence, config, episodes=episodes)
    assert AWAY not in decision.labels.tolist()
    assert decision.spells == [(0, n_frames, HOME)]


def test_a_long_control_episode_is_a_possession_of_its_own(evidence_factory, config):
    """The same blip, long enough to be controlled possession, does change hands."""
    long_run, _short_run, _long_gap = _sizes(config)
    away_run = config.min_control_frames + 20
    n_frames = 2 * long_run + away_run

    d_home = np.full(n_frames, 1.0, dtype=np.float32)
    d_away = np.full(n_frames, 10.0, dtype=np.float32)
    d_home[long_run:long_run + away_run] = 10.0
    d_away[long_run:long_run + away_run] = 1.0

    evidence = evidence_factory(n_frames, d_home=d_home, d_away=d_away)
    owners, _episodes = assign_owners(evidence, config)

    assert owners[long_run - 1] == HOME
    assert owners[long_run + away_run // 2] == AWAY
    assert owners[-1] == HOME


# --------------------------------------------------------------------------------------------------
# build_spells
# --------------------------------------------------------------------------------------------------


def test_build_spells_merges_runs_shorter_than_min_spell_frames(evidence_factory, config):
    """A possession too short to be one is merged into its neighbour."""
    long_run, _short_run, _long_gap = _sizes(config)
    short = max(1, config.min_spell_frames - 1)
    evidence = evidence_factory(2 * long_run + short)
    owners = np.array([HOME] * long_run + [AWAY] * short + [HOME] * long_run, dtype=np.int8)

    decision = build_spells(owners, evidence, config)

    assert set(decision.labels.tolist()) == {HOME}
    assert decision.spells == [(0, 2 * long_run + short, HOME)]


def test_build_spells_keeps_a_run_of_exactly_min_spell_frames(evidence_factory, config):
    long_run, _short_run, _long_gap = _sizes(config)
    spell = config.min_spell_frames
    evidence = evidence_factory(2 * long_run + spell)
    owners = np.array([HOME] * long_run + [AWAY] * spell + [HOME] * long_run, dtype=np.int8)

    decision = build_spells(owners, evidence, config)

    assert decision.spells == [
        (0, long_run, HOME),
        (long_run, long_run + spell, AWAY),
        (long_run + spell, 2 * long_run + spell, HOME),
    ]


def test_build_spells_merges_a_short_dead_run_between_the_same_team(evidence_factory, config):
    """`H H D H` with a two-frame `D` is one possession: the stoppage was noise."""
    long_run, _short_run, _long_gap = _sizes(config)
    short = max(1, config.min_spell_frames - 1)
    evidence = evidence_factory(2 * long_run + short)
    owners = np.array([HOME] * long_run + [DEAD] * short + [HOME] * long_run, dtype=np.int8)

    decision = build_spells(owners, evidence, config)

    assert decision.spells == [(0, 2 * long_run + short, HOME)]


def test_build_spells_keeps_a_short_dead_run_between_two_different_teams(evidence_factory, config):
    """`H H D A`: the stoppage is real, and it separates the two possessions."""
    long_run, _short_run, _long_gap = _sizes(config)
    short = max(1, config.min_spell_frames - 1)
    evidence = evidence_factory(2 * long_run + short)
    owners = np.array([HOME] * long_run + [DEAD] * short + [AWAY] * long_run, dtype=np.int8)

    decision = build_spells(owners, evidence, config)

    assert decision.spells == [
        (0, long_run, HOME),
        (long_run, long_run + short, DEAD),
        (long_run + short, 2 * long_run + short, AWAY),
    ]


def test_build_spells_keeps_the_owners_it_was_given(evidence_factory, config):
    """The spells are the labels; the owners are the frame-level answer underneath."""
    evidence = evidence_factory(85)
    owners = np.array([HOME] * 40 + [AWAY] * 45, dtype=np.int8)

    decision = build_spells(owners, evidence, config)

    assert decision.owners is owners
    assert decision.labels.tolist() == owners.tolist()


def test_build_spells_labels_an_unknown_owner_as_abstaining(evidence_factory, config):
    evidence = evidence_factory(10)
    owners = np.full(10, -1, dtype=np.int8)

    decision = build_spells(owners, evidence, config)

    assert set(decision.labels.tolist()) == {3}  # ABSTAIN
