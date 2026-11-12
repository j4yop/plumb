"""Turn raw tracking into the evidence a possession decision is made from.

One deep module at the evidence seam: :func:`build_evidence` returns an :class:`Evidence` object
holding every per-frame quantity the decision needs. The decision modules never see coordinates;
they see distances, activity, phases and absence classes.

The separation matters because the two sides of this problem fail in opposite ways. The *geometry*
side (who is nearest the ball) is mostly reliable but produces flicker. The *state* side (is the
ball alive, is the match running) is where the truth is decided, and it is invisible in the
coordinates alone — the ball is absent on 40.69% of graded frames, and it is *present* on 94% of
halftime frames while twelve players warm up.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import (
    BALL_OBSERVED,
    Config,
    OCCLUSION,
    OUT_OF_PLAY,
    STOPPAGE,
    WARMUP,
)


@dataclass
class Evidence:
    """Per-frame evidence. All arrays have length ``n_frames``."""

    n_frames: int
    # ball
    ball_present: np.ndarray  # bool
    ball_speed: np.ndarray  # float32, NaN where unknown
    ball_out_of_play: np.ndarray  # bool: last observation was outside the pitch
    # geometry
    d_home: np.ndarray  # distance to the nearest present home player (inf if none)
    d_away: np.ndarray
    near_team: np.ndarray  # int8: 0 home, 1 away, -1 nobody
    near_dist: np.ndarray
    players_home: np.ndarray  # int16 counts
    players_away: np.ndarray
    # motion
    activity: np.ndarray  # mean speed of present players, m/s
    moving_players: np.ndarray  # count of present players faster than run_speed_mps
    # context
    phase: np.ndarray  # int8 phase code
    graded: np.ndarray  # bool: the organisers score this frame
    warmup: np.ndarray  # bool: graded but not play (second-half pre-kickoff)
    # conclusion
    absence_class: np.ndarray  # int8 absence class code
    set_piece: np.ndarray  # bool: inside a Smart Tagging set-piece window
    # Whether the ball is not in play. Optional: when it is None the decision stage derives it
    # from the absence class.
    dead: np.ndarray = None
    # Distance from each team to the last known ball position. Optional: only the (disabled)
    # convergence hand-over experiment needs them.
    d_last_home: np.ndarray = None
    d_last_away: np.ndarray = None


def _distances(match, config: Config):
    """Distance from the ball to every tracked player, with unobserved slots pushed to infinity."""
    present = np.isfinite(match.player_xy[:, :, 0]) & np.isfinite(match.player_xy[:, :, 1])
    ball_x = match.ball_xy[:, 0]
    ball_y = match.ball_xy[:, 1]

    dx = ball_x[:, None] - match.player_xy[:, :, 0]
    dy = ball_y[:, None] - match.player_xy[:, :, 1]
    dist = np.sqrt(dx * dx + dy * dy, dtype=np.float32)
    dist[~present] = np.inf
    dist[~np.isfinite(ball_x)] = np.inf
    return dist, present


def _phase_array(n_frames: int, config: Config) -> np.ndarray:
    phase = np.empty(n_frames, dtype=np.int8)
    for frame in range(n_frames):
        phase[frame] = config.phase_of(frame)
    return phase


def _set_piece_mask(match, config: Config) -> np.ndarray:
    mask = np.zeros(match.n_frames, dtype=bool)
    for start, end, _kind in match.set_pieces:
        lo = max(0, start - config.set_piece_window_slack_frames)
        hi = min(match.n_frames, end + config.set_piece_window_slack_frames)
        mask[lo:hi] = True
    return mask


def build_evidence(match, config: Config, teams: np.ndarray = None) -> Evidence:
    """Compute every per-frame quantity the decision needs.

    The heavy lifting is one broadcast of the distance matrix: ``n_frames x n_slots`` float32,
    about 37 MB for the tactical recording, which is the price of vectorising the geometry.

    ``teams`` is the optional per-frame team membership from :mod:`mtah.teams`. When it is given,
    the static metadata assignment is not used at all.
    """
    n = match.n_frames
    dist, present = _distances(match, config)

    if teams is None:
        home_mask = np.broadcast_to((match.slot_team == 0), (n, match.n_slots))
        away_mask = np.broadcast_to((match.slot_team == 1), (n, match.n_slots))
    else:
        home_mask = teams == 0
        away_mask = teams == 1

    d_home = np.where(home_mask, dist, np.inf).min(axis=1)
    d_away = np.where(away_mask, dist, np.inf).min(axis=1)

    near_team = np.full(n, -1, dtype=np.int8)
    near_dist = np.minimum(d_home, d_away)
    both = np.isfinite(near_dist)
    near_team[both & (d_home <= d_away)] = 0
    near_team[both & (d_away < d_home)] = 1

    players_home = (present & home_mask).sum(axis=1).astype(np.int16)
    players_away = (present & away_mask).sum(axis=1).astype(np.int16)

    # Motion. Player speed is NaN for a missing observation, so the mean is over the players we can
    # actually see, and a frame with nobody visible has no activity rather than zero activity.
    speed = match.player_speed
    speed_ok = present & np.isfinite(speed)
    counts = speed_ok.sum(axis=1)
    speed_sum = np.where(speed_ok, speed, 0.0).sum(axis=1)
    activity = np.where(counts > 0, speed_sum / np.maximum(counts, 1), np.nan).astype(np.float32)
    moving = (speed_ok & (speed > config.run_speed_mps)).sum(axis=1).astype(np.int16)

    ball_present = np.isfinite(match.ball_xy[:, 0]) & np.isfinite(match.ball_xy[:, 1])

    # The last known ball position, carried forward. During an occlusion it is the only handle
    # we have on where the ball went, so it is worth keeping.
    filled_xy = match.ball_xy.copy()
    last = np.array([np.nan, np.nan], dtype=np.float32)
    for frame in range(n):
        if ball_present[frame]:
            last = match.ball_xy[frame]
        filled_xy[frame] = last
    dx = filled_xy[:, 0][:, None] - match.player_xy[:, :, 0]
    dy = filled_xy[:, 1][:, None] - match.player_xy[:, :, 1]
    to_last = np.sqrt(dx * dx + dy * dy, dtype=np.float32)
    to_last[~present] = np.inf
    d_last_home = np.where(home_mask, to_last, np.inf).min(axis=1)
    d_last_away = np.where(away_mask, to_last, np.inf).min(axis=1)

    # "Out of play": the last observed ball position was outside the pitch rectangle. We track the
    # last observation forward, so a ball that leaves the pitch stays flagged until we see it
    # again — which is exactly the behaviour we want for a throw-in or a goal kick.
    out_of_play = np.zeros(n, dtype=bool)
    last_x = np.nan
    last_y = np.nan
    for frame in range(n):
        if ball_present[frame]:
            last_x = match.ball_xy[frame, 0]
            last_y = match.ball_xy[frame, 1]
            out_of_play[frame] = (
                last_x < -config.out_of_play_slack_m
                or last_x > config.pitch_length_m + config.out_of_play_slack_m
                or last_y < -config.out_of_play_slack_m
                or last_y > config.pitch_width_m + config.out_of_play_slack_m
            )
        else:
            out_of_play[frame] = (
                not np.isnan(last_x)
                and (
                    last_x < -config.out_of_play_slack_m
                    or last_x > config.pitch_length_m + config.out_of_play_slack_m
                    or last_y < -config.out_of_play_slack_m
                    or last_y > config.pitch_width_m + config.out_of_play_slack_m
                )
            )

    phase = _phase_array(n, config)
    graded = np.array([config.is_graded(frame) for frame in range(n)], dtype=bool)
    warmup = np.array([config.is_warmup(frame) for frame in range(n)], dtype=bool)
    set_piece = _set_piece_mask(match, config)

    # Absence classification. The order matters: a warm-up is a warm-up even if the ball happens to
    # be visible, and a ball out of play is dead regardless of how much the players are moving.
    #
    # The test is deliberately conservative. Measured against the organisers' labels, "the ball is
    # not tracked and almost nobody is running" identifies dead ball with 96% precision, while a
    # false dead-ball period is the expensive mistake: it splits a real possession in two.
    absence = np.full(n, BALL_OBSERVED, dtype=np.int8)
    for frame in range(n):
        if ball_present[frame]:
            continue
        if warmup[frame]:
            absence[frame] = WARMUP
        elif moving[frame] <= config.dead_movers:
            absence[frame] = OUT_OF_PLAY if out_of_play[frame] else STOPPAGE
        else:
            absence[frame] = OCCLUSION

    dead = np.isin(absence, (STOPPAGE, OUT_OF_PLAY, WARMUP))

    return Evidence(
        n_frames=n,
        ball_present=ball_present,
        ball_speed=match.ball_speed,
        ball_out_of_play=out_of_play,
        d_last_home=d_last_home.astype(np.float32),
        d_last_away=d_last_away.astype(np.float32),
        d_home=d_home.astype(np.float32),
        d_away=d_away.astype(np.float32),
        near_team=near_team,
        near_dist=near_dist.astype(np.float32),
        players_home=players_home,
        players_away=players_away,
        activity=activity,
        moving_players=moving,
        phase=phase,
        graded=graded,
        warmup=warmup,
        absence_class=absence,
        dead=dead,
        set_piece=set_piece,
    )
