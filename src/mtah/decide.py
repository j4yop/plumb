"""Decide the label for every frame: who has the ball, or that the ball is dead.

The rules below were designed from the football and then checked against the organisers' five
public minutes as a *semantic* check — the labels the organisers use for a dead ball, for a
change of possession, and for a possession that has just started.

Four measurements shaped this module:

1. **Dead ball is a play-state, not a missing ball.** In the public window the ball is *visible*
   in two thirds of the frames the organisers call dead, so "the ball is not tracked" cannot be
   the test. What does separate them: at a dead ball the players are not running (3.4 of them
   moving faster than 2 m/s, against 10.7 during live play) and nobody is near the ball. The
   combined test "ball not tracked **and** almost nobody is running" is 96% precise. The
   asymmetry matters as much as the precision: a false dead-ball period splits a real possession
   in two, while a missed one only makes a possession slightly too long — and temporal IoU
   forgives that. **So the detector is deliberately conservative.**

2. **A change of possession is a change of *control*, sustained.** The organisers' definition: the
   opponent must gain *controlled* possession — not touch it, not deflect it, not win an aerial
   duel. Control is proxied by distance, and the crucial part is that it has to *persist*.

3. **Deciding frame by frame is the mistake.** Our first version decided ownership per frame and
   it shattered a single 41-second truth possession into seven pieces: a pass that passed within
   two metres of a defender flipped the owner for a frame or two and each flip became another
   possession to be matched. Since the metric counts possessions, every blip is scored as a
   spurious possession. So ownership is decided on **episodes** — maximal runs of frames in which
   the same team is the nearer one — and short episodes are absorbed into their neighbours before
   they can become possessions.

4. **The ball is missing 41% of the time.** A hand-over must not depend on seeing the ball, so a
   short stretch of untracked frames does not interrupt an episode, and the last owner keeps the
   ball until the evidence says otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from .config import (
    ABSTAIN,
    AWAY,
    Config,
    DEAD,
    HOME,
    OUT_OF_PLAY,
    STOPPAGE,
    WARMUP,
)


@dataclass
class Decision:
    """The outcome of the decision stage."""

    labels: np.ndarray  # int8 per frame: HOME / AWAY / DEAD / ABSTAIN
    owners: np.ndarray  # int8 per frame: HOME / AWAY / DEAD / -1 unknown
    spells: List[Tuple[int, int, int]]  # (start_frame, stop_frame, label), half-open
    episodes: List[Tuple[int, int, int]]  # the control episodes the owners were derived from


def _owner_signal(evidence, config: Config) -> np.ndarray:
    """Per frame: which team appears to have the ball under control, or -1 when nobody has it.

    Control is the organisers' own word: the ball has to be within the control radius of one
    team's player and outside it of the other's. If both teams have somebody inside it, the ball
    is contested and nobody controls it; if neither does, the ball is loose or in flight. In both
    cases the signal is empty and the previous owner keeps the ball.

    The team also has to be **clearly** nearer — by at least the hand-over margin. Without that
    requirement a pass that travels within a metre of a defender counts as a change of
    possession, and each such near-miss becomes another possession for the scorer to punish.
    """
    signal = np.full(evidence.n_frames, -1, dtype=np.int8)
    radius = config.control_radius_m

    with np.errstate(invalid="ignore"):
        home_controls = evidence.d_home <= radius
        away_controls = evidence.d_away <= radius
        exclusive = home_controls ^ away_controls

        home_clear = exclusive & home_controls & (
            (evidence.d_away - evidence.d_home) >= config.handover_margin_m
        )
        away_clear = exclusive & away_controls & (
            (evidence.d_home - evidence.d_away) >= config.handover_margin_m
        )

    signal[home_clear] = HOME
    signal[away_clear] = AWAY
    # The ball has to be observed at all for either team to control it.
    signal[~evidence.ball_present] = -1
    return signal


def _fill_short_gaps(signal: np.ndarray, max_gap: int) -> np.ndarray:
    """Bridge short stretches with no signal when both sides agree.

    The ball goes missing for a moment all the time — a crowd, a shadow, a kick. If the team on
    one side of the gap is the same as the team on the other side, the gap is an occlusion
    inside one possession, not a change of possession.
    """
    out = signal.copy()
    index = 0
    n = signal.shape[0]
    while index < n:
        if signal[index] != -1:
            index += 1
            continue
        start = index
        while index < n and signal[index] == -1:
            index += 1
        stop = index
        if stop - start > max_gap:
            continue
        before = signal[start - 1] if start > 0 else -1
        after = signal[stop] if stop < n else -1
        if before != -1 and before == after:
            out[start:stop] = before
    return out


def _episodes(signal: np.ndarray) -> List[Tuple[int, int, int]]:
    """Maximal runs of the same signal, as ``(start, stop, team)`` half-open."""
    episodes: List[Tuple[int, int, int]] = []
    index = 0
    n = signal.shape[0]
    while index < n:
        team = signal[index]
        stop = index + 1
        while stop < n and signal[stop] == team:
            stop += 1
        if team != -1:
            episodes.append((index, stop, int(team)))
        index = stop
    return episodes


def _merge_episodes(episodes: List[Tuple[int, int, int]], min_length: int) -> List[Tuple[int, int, int]]:
    """Absorb episodes that are too short to be a possession into their neighbours.

    If the neighbours agree, the short episode was a blip between them. If they disagree, the
    short episode loses to whichever neighbour is longer — a possession change is a sustained
    rearrangement of who is nearest the ball, not a frame or two.
    """
    if not episodes:
        return []
    merged: List[Tuple[int, int, int]] = []
    index = 0
    count = len(episodes)
    while index < count:
        start, stop, team = episodes[index]
        length = stop - start
        if length >= min_length or count == 1:
            merged.append((start, stop, team))
            index += 1
            continue

        previous = merged[-1] if merged else None
        following = episodes[index + 1] if index + 1 < count else None

        if previous is not None and following is not None and previous[2] == following[2]:
            # A blip between two stretches of the same team.
            merged[-1] = (previous[0], following[1], previous[2])
            index += 1
            continue
        if previous is None and following is not None:
            # The first episode of a phase: it has no predecessor, so it keeps its own team.
            merged.append((start, stop, team))
            index += 1
            continue
        if following is None and previous is not None:
            merged[-1] = (previous[0], stop, previous[2])
            index += 1
            continue
        if previous is not None and following is not None:
            # Different neighbours: the short episode loses to the longer one.
            previous_length = previous[1] - previous[0]
            following_length = following[1] - following[0]
            if previous_length >= following_length:
                merged[-1] = (previous[0], stop, previous[2])
                index += 1
            else:
                merged.append((start, following[1], following[2]))
                index += 1
            continue
        merged.append((start, stop, team))
        index += 1
    return merged


def control_episodes(evidence, config: Config):
    """The control episodes the ownership is built from.

    An episode is a maximal run of frames in which one team appears to have the ball under
    control. Short episodes are absorbed into their neighbours, because a possession change is
    something that persists and a pass that went near an opponent is not.
    """
    signal = _owner_signal(evidence, config)
    signal = _fill_short_gaps(signal, config.max_signal_gap_frames)
    return signal, _merge_episodes(_episodes(signal), config.min_control_frames)


def assign_owners(evidence, config: Config) -> Tuple[np.ndarray, List[Tuple[int, int, int]]]:
    """Per-frame owner, and the control episodes behind it.

    Per-frame owner: 0 home, 1 away, 2 dead, -1 unknown.

    The state machine, frame by frame:

    1. A dead frame — the ball is not in play — is dead: it breaks the possession.
    2. The ball is not tracked but the match is running: an occlusion. The last owner keeps the
       ball, because the organisers' ground truth is derived from the *corrected* tracking, and
       an occlusion during live play is still somebody's possession.
    3. The ball is tracked. Control goes to the team whose nearest player is within the control
       radius, provided the other team has nobody inside it — otherwise the ball is contested and
       the current owner keeps it.
    4. Control changes hands only after the minimum dwell, and only when the new team is
       *clearly* nearer, so a touch or a deflection does not move the ball.
    """
    n = evidence.n_frames
    owners = np.full(n, -1, dtype=np.int8)

    _signal, episodes = control_episodes(evidence, config)
    for start, stop, team in episodes:
        owners[start:stop] = team

    # Dead frames break the possession; a frame that is neither dead nor covered by an episode
    # keeps the last owner.
    dead = (
        evidence.dead
        if evidence.dead is not None
        else np.isin(evidence.absence_class, (STOPPAGE, OUT_OF_PLAY, WARMUP))
    )
    current = -1
    pending_challenger = -1
    pending_count = 0

    for frame in range(n):
        if not evidence.graded[frame]:
            owners[frame] = -1
            current = -1
            pending_challenger = -1
            pending_count = 0
            continue
        if dead[frame]:
            owners[frame] = DEAD
            current = -1
            pending_challenger = -1
            pending_count = 0
            continue
        if owners[frame] != -1:
            owners[frame] = int(owners[frame])
            current = int(owners[frame])
            pending_challenger = -1
            pending_count = 0
            continue

        # No control signal: the ball is untracked, or contested.
        owners[frame] = current

        if (
            config.convergence_handover
            and current != -1
            and not evidence.ball_present[frame]
            and evidence.d_last_home is not None
        ):
            # During an occlusion the only handle on where the ball went is its last known
            # position, and the team whose players close in on it is the team contesting it.
            d_new = evidence.d_last_home[frame] if current == AWAY else evidence.d_last_away[frame]
            d_old = evidence.d_last_home[frame] if current == HOME else evidence.d_last_away[frame]
            challenger = AWAY if current == HOME else HOME
            if (
                np.isfinite(d_new)
                and d_new <= config.reach_radius_m
                and d_old - d_new >= config.handover_margin_m
            ):
                if pending_challenger == challenger:
                    pending_count += 1
                else:
                    pending_challenger = challenger
                    pending_count = 1
                if pending_count >= config.min_dwell_frames:
                    current = challenger
                    pending_challenger = -1
                    pending_count = 0
                    owners[frame] = current
            else:
                pending_challenger = -1
                pending_count = 0

    return owners, episodes


def _runs(labels: np.ndarray) -> List[Tuple[int, int, int]]:
    """Maximal constant-label runs as ``(start, stop, label)``, half-open."""
    if labels.size == 0:
        return []
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [labels.size]))
    return [(int(a), int(b), int(labels[a])) for a, b in zip(starts, stops)]


def build_spells(owners: np.ndarray, evidence, config: Config,
                 episodes=None) -> Decision:
    """Turn owners into spells, merging the ones that are too short to be possessions.

    A possession is a maximal run of one team with the ball alive, so a run shorter than the
    minimum spell duration is not a possession: it is noise, and it is removed by merging it into
    its neighbour. If both neighbours are the same team the run was a blip between them; if they
    differ the short run loses to the established possession.

    Dead-ball runs are treated more carefully: a very short dead run *between* the same team is
    noise, but a short dead run at the edge of a possession is a real stoppage and is kept.
    """
    labels = np.empty(owners.shape[0], dtype=np.int8)
    labels[:] = ABSTAIN
    labels[owners == HOME] = HOME
    labels[owners == AWAY] = AWAY
    labels[owners == DEAD] = DEAD

    runs = _runs(labels)

    for index, (start, stop, label) in enumerate(runs):
        length = stop - start
        if length >= config.min_spell_frames:
            continue
        previous = runs[index - 1][2] if index > 0 else None
        following = runs[index + 1][2] if index + 1 < len(runs) else None

        if label == DEAD:
            if previous is not None and previous == following:
                labels[start:stop] = previous
            continue

        if previous is None:
            # The first run of a phase has no neighbour to merge with. It keeps its own label:
            # a short opening possession is a possession, and merging it into the run that
            # follows would also move the phase boundary to the wrong team.
            continue

        if following is None:
            # The last run of a phase: it merges into the possession before it.
            labels[start:stop] = previous
            continue

        if previous == following:
            # A blip between two stretches of the same team.
            labels[start:stop] = previous
        else:
            # Different neighbours: the short run loses to the established possession.
            labels[start:stop] = previous

    if config.smoothing_window_frames > 1:
        labels = _majority_smooth(labels, config.smoothing_window_frames)

    if episodes is None:
        episodes = control_episodes(evidence, config)[1]
    spells = _runs(labels)
    return Decision(labels=labels, owners=owners, spells=spells, episodes=episodes)


def _majority_smooth(labels: np.ndarray, window: int) -> np.ndarray:
    """Centred majority vote, ties resolved towards the previous label."""
    half = window // 2
    out = labels.copy()
    for index in range(labels.shape[0]):
        lo = max(0, index - half)
        hi = min(labels.shape[0], index + half + 1)
        window_labels = labels[lo:hi]
        counts = np.bincount(window_labels, minlength=4)
        if counts.max() == 1:
            out[index] = labels[index]
        else:
            best = int(counts.argmax())
            if best == ABSTAIN and counts[labels[index]] == counts.max():
                best = int(labels[index])
            out[index] = best
    return out
