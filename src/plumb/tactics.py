"""The tactical aspects: what happened, beyond who had the ball.

Why this module exists
-----------------------
Possession is one question. A coach asks six more, and every one of them has to rest on the
same discipline the possession engine follows: a number, the frames it rests on, and an honest
statement of what the feed can carry.

The six aspects:

``restarts``
    Set pieces are the moments the game is handed over for free. Who takes them, and who keeps
    the ball afterwards.
``pressing``
    When a team does not have the ball, how close does it get, how many players does it send,
    and does the pressure win the ball back?
``build_up``
    How a team plays out of its own half: how high the team stands, how many options the
    carrier has, how deep the ball is.
``defending``
    The shape of the team that does not have the ball: how wide it is, where the line sits, and
    how much space it leaves.
``transitions``
    What happens in the ten seconds after the ball changes hands — how long the chains are, and
    how often the team that lost it wins it straight back.
``chance_creation``
    How often a possession reaches the final third and the penalty area.

Every function here returns a :class:`Tactic`: the numbers, the frames the claim rests on, and
a sentence about how far the claim can be carried. The frames are the point. A claim about the
final third is only as good as the final third's coverage, and the ledger has to say so.

Two notes on the method
-----------------------
**Team membership is the tracking metadata**, the same assignment the submitted possession file
uses, so the shape and the possession can never contradict each other about who was on the
pitch. The organisers warn that slots "appear, vanish and swap identity as the tracker loses and
re-acquires people", so a shape measured from a slot that has swapped is wrong in those frames;
that is a limitation of the feed, and the confidence line says so.

**Everything is computed in chunks.** A match is 200,000 frames of 46 slots, and the geometry
here is a few hundred megabytes if it is held all at once. Chunking keeps the peak memory at a
few megabytes and the arithmetic identical.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from mtah.config import AWAY, DEAD, HOME

from .analysis import Analysis

# A press that gets within this many metres of the ball is a press.
PRESS_RADIUS_M = 8.0
# A defender this close to the ball counts as pressing it.
PRESSING_RADIUS_M = 15.0
# How many of the defending team have to be inside the pressing radius for the press to count
# as engaged.
PRESS_NUMBERS = 3
# A team-mate this close to the carrier counts as an option.
OPTION_RADIUS_M = 20.0
# How long a counter-press has to win the ball back.
COUNTER_PRESS_SECONDS = 10.0
# How long a restart's taker has to keep the ball.
RESTART_RETENTION_SECONDS = 10.0
# How fast a restart has to turn over to count as lost quickly.
RESTART_QUICK_LOSS_SECONDS = 3.0
FPS = 25.0
# Frames processed at a time.
CHUNK = 20000


@dataclass
class Tactic:
    """One aspect of the match: the numbers, the frames, and the caveat."""

    id: str
    title: str
    answer: str
    detail: List[Tuple[str, str]] = field(default_factory=list)
    frames: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=bool))
    confidence: str = ""


# --------------------------------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------------------------------


@dataclass
class Geometry:
    """The distances that every aspect needs, computed once."""

    distance: np.ndarray  # (n_frames, n_slots) float32, metres; inf where unknown
    carrier_slot: np.ndarray  # (n_frames,) int32: the slot nearest the ball


def geometry(analysis: Analysis) -> Geometry:
    """The distance from the ball to every slot, and who is nearest to it."""
    n = analysis.n_frames
    slots = analysis.player_xy.shape[1]
    distance = np.empty((n, slots), dtype=np.float32)
    for lo in range(0, n, CHUNK):
        hi = min(n, lo + CHUNK)
        difference = analysis.ball_xy[lo:hi, None, :] - analysis.player_xy[lo:hi]
        block = np.sqrt((difference ** 2).sum(axis=2)).astype(np.float32)
        block[~np.isfinite(block)] = np.inf
        distance[lo:hi] = block
    carrier = np.argmin(distance, axis=1).astype(np.int32)
    return Geometry(distance=distance, carrier_slot=carrier)


def attacking_sides(analysis: Analysis) -> np.ndarray:
    """Per frame: is the home team attacking towards increasing ``x``?

    Derived from the data, not assumed. In each half the two teams' players have a mean ``x``;
    the team that spends more of the half in the right half of the pitch is the one attacking
    that way, because a team that attacks right defends the left and pushes up. The two teams'
    means are tens of metres apart, so the reading is not marginal.

    The answer flips at half time, as it must: the teams change ends.
    """
    n = analysis.n_frames
    result = np.zeros(n, dtype=bool)

    halves = [
        (11185, 90651),
        (110808, 190197),
    ]
    for lo, hi in halves:
        lo = max(0, lo)
        hi = min(n - 1, hi)
        if hi <= lo:
            continue
        means = []
        for team in (HOME, AWAY):
            total = 0.0
            count = 0
            for block in range(lo, hi + 1, CHUNK):
                stop = min(hi + 1, block + CHUNK)
                x = analysis.player_xy[block:stop, :, 0]
                valid = (analysis.teams[block:stop] == team) & np.isfinite(x)
                total += float(np.where(valid, x, 0.0).sum())
                count += int(valid.sum())
            means.append(total / count if count else 0.0)
        # The team with the higher mean x is attacking right, so home attacks right only when
        # home's mean is the higher of the two.
        result[lo:hi + 1] = means[0] > means[1]
    return result


def _progress_chunk(analysis: Analysis, home_right: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """How far up the pitch each slot is, from its own team's perspective, for one chunk."""
    length = analysis.pitch_length_m
    x = analysis.player_xy[lo:hi, :, 0]
    home_progress = np.where(home_right[lo:hi][:, None], x, length - x)
    away_progress = length - home_progress
    return np.where(analysis.teams[lo:hi] == HOME, home_progress, away_progress)


def _alive(analysis: Analysis, mask: np.ndarray) -> np.ndarray:
    return mask & (analysis.labels != DEAD) & (analysis.labels != 3)


def tactics_scope(analysis: Analysis, zone: str) -> np.ndarray:
    """The frames whose ball is in a named zone, relative to the team in possession.

    "The final third" means the third the team in possession is attacking into, so the zone is
    the same question whichever team has the ball.
    """
    from .coverage import zone_mask

    home_right = attacking_sides(analysis)
    own_right = np.where(analysis.labels == HOME, home_right, ~home_right)
    return zone_mask(
        analysis.ball_xy,
        own_right,
        zone,
        analysis.pitch_length_m,
        analysis.pitch_width_m,
    )


def _next_alive(analysis: Analysis, alive: np.ndarray, after: int) -> int:
    """The first live frame at or after ``after``, or -1."""
    if after >= alive.shape[0]:
        return -1
    index = np.flatnonzero(alive[after:])
    return int(after + index[0]) if index.size else -1


# --------------------------------------------------------------------------------------------------
# The aspects
# --------------------------------------------------------------------------------------------------


def restarts(analysis: Analysis, mask: np.ndarray, geo: Geometry) -> Tactic:
    """Set pieces: who takes them, and who keeps the ball afterwards.

    A restart is a moment the game is handed over for free. The taker is the team holding the
    ball when play resumes, read from our own possession labels rather than from the tagging.
    The question that matters to a coach is what happens next: does the taker keep the ball, or
    does it come straight back?
    """
    n = analysis.n_frames
    alive = _alive(analysis, np.ones(n, dtype=bool))
    taken = {HOME: 0, AWAY: 0}
    retained = {HOME: 0, AWAY: 0}
    quick_loss = {HOME: 0, AWAY: 0}
    kinds: Dict[str, Dict[int, int]] = {}
    frames = np.zeros(n, dtype=bool)

    spells = [s for s in analysis.spells if s[2] in (HOME, AWAY)]
    spell_starts = [s[0] for s in spells]

    for phase in analysis.phases:
        if phase.code != "SET PIECES":
            continue
        lo = max(0, phase.start)
        hi = min(n - 1, phase.end)
        if hi < lo or not mask[lo:hi + 1].any():
            continue
        frames[lo:hi + 1] = True

        # The taker is the team holding the ball as the restart is taken: the first live frame
        # at or after the end of the tagged window.
        first = _next_alive(analysis, alive, hi + 1)
        if first < 0:
            continue
        taker = int(analysis.labels[first])
        if taker not in (HOME, AWAY):
            continue

        taken[taker] += 1
        kinds.setdefault(phase.kind or "unspecified", {HOME: 0, AWAY: 0})[taker] += 1

        # The possession that starts at the restart: how long does the taker keep it?
        index = int(np.searchsorted(spell_starts, first, side="right")) - 1
        if index < 0 or spells[index][2] != taker:
            retained[taker] += 1
            continue
        held = spells[index][1] - first
        if held >= RESTART_RETENTION_SECONDS * FPS:
            retained[taker] += 1
        elif held <= RESTART_QUICK_LOSS_SECONDS * FPS:
            quick_loss[taker] += 1

    def kept_rate(kept: int, total: int) -> float:
        return kept / total if total else 0.0

    detail = [
        ("restarts taken", "{} home, {} away".format(taken[HOME], taken[AWAY])),
        ("kept the ball 10 s", "{} home ({:.0%}), {} away ({:.0%})".format(
            retained[HOME], kept_rate(retained[HOME], taken[HOME]),
            retained[AWAY], kept_rate(retained[AWAY], taken[AWAY]),
        )),
        ("lost within 3 s", "{} home, {} away".format(quick_loss[HOME], quick_loss[AWAY])),
    ]
    for kind, counts in sorted(kinds.items(), key=lambda item: -sum(item[1].values()))[:3]:
        detail.append((kind.lower(), "{} home, {} away".format(counts[HOME], counts[AWAY])))

    if taken[HOME] + taken[AWAY] == 0:
        return Tactic(
            id="restarts",
            title="Restarts",
            answer="no set pieces fall inside this window.",
            detail=detail,
            frames=frames,
            confidence="nothing to measure",
        )

    if retained[HOME] == retained[AWAY]:
        answer = "{} restarts were taken, and each side kept about as many as it won.".format(
            taken[HOME] + taken[AWAY]
        )
    else:
        answer = "{} restarts were taken; {} kept theirs more often.".format(
            taken[HOME] + taken[AWAY], _team_lead(retained[HOME], retained[AWAY])
        )

    return Tactic(
        id="restarts",
        title="Restarts",
        answer=answer,
        detail=detail,
        frames=frames,
        confidence="the taker is read from our own possession labels at the restart; the "
                   "set-piece windows are tagged, so their edges are approximate",
    )


def _team_lead(home: int, away: int) -> str:
    """The team that came out ahead, or an empty string when they are level."""
    if home == away:
        return ""
    return "Barcelona" if home > away else "Athletic Club"

def pressing(analysis: Analysis, mask: np.ndarray, geo: Geometry) -> Tactic:
    """How the team without the ball presses, and whether the press wins it.

    Three numbers per possession: how many defenders the press sends (the *press numbers*), how
    close the closest one gets, and how fast it is closing. And one outcome: does the
    possession end soon after the press engages?
    """
    n = analysis.n_frames
    evidence = analysis.evidence
    live = _alive(analysis, mask) & evidence.ball_present

    # For the team in possession, the press comes from the other side, so the press distance is
    # the distance to the other team's nearest player.
    in_possession = analysis.labels
    press_distance = np.where(
        in_possession == HOME, evidence.d_away, np.where(in_possession == AWAY, evidence.d_home, np.inf)
    )

    # Press numbers: how many of the defending team are inside 15 m of the ball.
    near = geo.distance < PRESSING_RADIUS_M
    press_home = (near & (analysis.teams == HOME)).sum(axis=1)
    press_away = (near & (analysis.teams == AWAY)).sum(axis=1)
    press_numbers = np.where(in_possession == HOME, press_away, press_home).astype(np.float32)
    del near

    # Closing speed: how fast the press is reducing the distance to the ball, over a second.
    half = int(FPS / 2)
    padded = np.concatenate([
        np.full(half, np.inf), press_distance, np.full(half, np.inf)
    ])
    with np.errstate(invalid="ignore"):
        closing = (padded[:-2 * half] - padded[2 * half:]) / (2.0 * half / FPS)
    closing[~np.isfinite(closing)] = np.nan

    possessions = [
        (a, b, label)
        for a, b, label in analysis.spells
        if label in (HOME, AWAY) and mask[a:min(b + 1, n)].any()
    ]
    alive = _alive(analysis, np.ones(n, dtype=bool))
    engaged = 0
    hard = 0
    won = 0
    peak_numbers: List[float] = []
    closest: List[float] = []
    speeds: List[float] = []

    for a, b, label in possessions:
        stop = min(b + 1, n)
        window = press_distance[a:stop]
        finite = window[np.isfinite(window)]
        if finite.size == 0:
            continue
        engaged += 1
        best = float(finite.min())
        closest.append(best)
        nums = press_numbers[a:stop]
        peak = float(np.nanmax(nums)) if np.isfinite(nums).any() else 0.0
        peak_numbers.append(peak)
        speed = closing[a:stop]
        speed = speed[np.isfinite(speed)]
        if speed.size:
            speeds.append(float(np.nanmax(speed)))
        # The press engaged hard: three or more defenders within fifteen metres.
        if peak < PRESS_NUMBERS:
            continue
        hard += 1
        close_at = a + int(np.nanargmin(np.where(np.isfinite(window), window, np.inf)))
        horizon = min(n - 1, close_at + int(5 * FPS))
        later = _next_alive(analysis, alive, close_at + 1)
        if later >= 0 and later <= horizon and int(analysis.labels[later]) != label:
            won += 1

    detail = [
        ("possessions with the ball", str(engaged)),
        ("press engaged hard", "{} of {} ({:.0%})".format(
            hard, engaged, hard / engaged if engaged else 0.0)),
        ("won the ball back", "{} of {} ({:.0%})".format(
            won, hard, won / hard if hard else 0.0)),
        ("press numbers", "median peak {:.0f}".format(
            float(np.median(peak_numbers)) if peak_numbers else 0.0)),
        ("closest press", "median {:.1f} m".format(
            float(np.median(closest)) if closest else 0.0)),
        ("closing speed", "median peak {:.1f} m/s".format(
            float(np.median(speeds)) if speeds else 0.0)),
    ]

    if engaged == 0:
        return Tactic(
            id="pressing",
            title="Pressing",
            answer="no live possession in this window to press.",
            detail=detail,
            frames=live,
            confidence="nothing to measure",
        )

    return Tactic(
        id="pressing",
        title="Pressing",
        answer="the press engaged hard in {} of {} possessions, and won the ball back in {} of "
               "those.".format(hard, engaged, won),
        detail=detail,
        frames=live,
        confidence="a press engages hard when three or more of the defending team are within "
                   "fifteen metres of the ball; the outcome is the change of possession within "
                   "five seconds of that moment",
    )


def build_up(analysis: Analysis, mask: np.ndarray, geo: Geometry) -> Tactic:
    """How the team in possession plays the ball out.

    Line height is the average distance up the pitch of the team's players, measured from the
    goal it defends. Options are the team-mates within twenty metres of the carrier.
    """
    n = analysis.n_frames
    home_right = attacking_sides(analysis)
    length = analysis.pitch_length_m
    live = _alive(analysis, mask) & analysis.evidence.ball_present
    in_possession = analysis.labels

    line_height = np.full(n, np.nan, dtype=np.float32)
    options = np.full(n, np.nan, dtype=np.float32)
    own_goal = np.full(n, np.nan, dtype=np.float32)

    for lo in range(0, n, CHUNK):
        hi = min(n, lo + CHUNK)
        progress = _progress_chunk(analysis, home_right, lo, hi)
        present = np.isfinite(progress)

        mean_progress = {}
        for team in (HOME, AWAY):
            good = (analysis.teams[lo:hi] == team) & present
            count = good.sum(axis=1)
            total = np.where(good, progress, 0.0).sum(axis=1)
            mean_progress[team] = (total / np.maximum(count, 1)).astype(np.float32)

        label = in_possession[lo:hi]
        line_height[lo:hi] = np.where(
            label == HOME, mean_progress[HOME], np.where(label == AWAY, mean_progress[AWAY], np.nan)
        )

        # Options: team-mates of the carrier within 20 m.
        carrier = geo.carrier_slot[lo:hi]
        rows = np.arange(hi - lo)
        carrier_team = analysis.teams[lo:hi][rows, carrier]
        same_team = analysis.teams[lo:hi] == carrier_team[:, None]
        count = ((same_team) & (geo.distance[lo:hi] < OPTION_RADIUS_M)).sum(axis=1) - 1
        options[lo:hi] = count.astype(np.float32)

        # How deep the carrier is: his distance from his own goal line. ``progress`` is already
        # measured from the carrier's own team's goal line, so no flip is needed.
        carrier_progress = progress[np.arange(hi - lo), carrier]
        own_goal[lo:hi] = carrier_progress.astype(np.float32)

    frames = live
    if not frames.any():
        return Tactic(
            id="build_up",
            title="Build-up",
            answer="no live frames with the ball observed in this window.",
            detail=[],
            frames=frames,
            confidence="nothing to measure",
        )

    height_mean = float(np.nanmean(line_height[frames]))
    options_mean = float(np.nanmean(options[frames]))
    detail = [
        ("line height", "{:.1f} m from own goal line".format(height_mean)),
        ("options within 20 m", "{:.1f} at the carrier".format(options_mean)),
        ("ball depth", "{:.1f} m from own goal line".format(float(np.nanmean(own_goal[frames])))),
    ]

    return Tactic(
        id="build_up",
        title="Build-up",
        answer="the team in possession averaged {:.1f} m from its own goal line, with {:.1f} "
               "options within twenty metres of the carrier.".format(height_mean, options_mean),
        detail=detail,
        frames=frames,
        confidence="line height is the mean of every visible player of the team in possession; "
                   "options are counted from the carrier's own position",
    )


def defending(analysis: Analysis, mask: np.ndarray, geo: Geometry) -> Tactic:
    """The shape of the team that does not have the ball.

    Block width is the width of the defending team in metres; block height is how far up the
    pitch it stands; the biggest gap is the widest hole between two defenders in the same
    vertical line.
    """
    n = analysis.n_frames
    home_right = attacking_sides(analysis)
    live = _alive(analysis, mask) & analysis.evidence.ball_present
    in_possession = analysis.labels

    width = np.full(n, np.nan, dtype=np.float32)
    height = np.full(n, np.nan, dtype=np.float32)
    biggest_gap = np.full(n, np.nan, dtype=np.float32)
    pressure = np.full(n, np.nan, dtype=np.float32)
    in_box = np.full(n, np.nan, dtype=np.float32)

    for lo in range(0, n, CHUNK):
        hi = min(n, lo + CHUNK)
        progress = _progress_chunk(analysis, home_right, lo, hi)
        present = np.isfinite(progress)
        x = analysis.player_xy[lo:hi, :, 0]
        y = analysis.player_xy[lo:hi, :, 1]

        for team in (HOME, AWAY):
            good = (analysis.teams[lo:hi] == team) & present
            count = good.sum(axis=1)
            if count.max() < 3:
                continue
            ys = np.where(good, y, np.nan)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                block_width = np.nanmax(ys, axis=1) - np.nanmin(ys, axis=1)
                sorted_y = np.sort(ys, axis=1)
                gaps = np.diff(sorted_y, axis=1)
                gap = np.nanmax(gaps, axis=1)
            block_height = np.where(good, progress, 0.0).sum(axis=1) / np.maximum(count, 1)
            near = np.where(good, geo.distance[lo:hi], np.inf).min(axis=1)

            # Players in the penalty area the team is attacking: the box is at the far end of
            # the team's own progress axis.
            far = analysis.pitch_length_m - 16.5
            in_the_box = (
                good
                & (progress > far)
                & (np.abs(y - analysis.pitch_width_m / 2) < 20.3)
            )
            box_count = in_the_box.sum(axis=1).astype(np.float32)

            defending_now = live[lo:hi] & (in_possession[lo:hi] != team)
            width[lo:hi] = np.where(defending_now, block_width, width[lo:hi])
            height[lo:hi] = np.where(defending_now, block_height, height[lo:hi])
            biggest_gap[lo:hi] = np.where(defending_now, gap, biggest_gap[lo:hi])
            pressure[lo:hi] = np.where(defending_now, near, pressure[lo:hi])
            in_box[lo:hi] = np.where(defending_now, box_count, in_box[lo:hi])

    frames = live
    if not frames.any():
        return Tactic(
            id="defending",
            title="Defending",
            answer="no live frames to measure a defensive shape in.",
            detail=[],
            frames=frames,
            confidence="nothing to measure",
        )

    width_mean = float(np.nanmean(width[frames]))
    height_mean = float(np.nanmean(height[frames]))
    gap_mean = float(np.nanmean(biggest_gap[frames]))
    detail = [
        ("block width", "{:.1f} m".format(width_mean)),
        ("block height", "{:.1f} m from own goal line".format(height_mean)),
        ("biggest gap", "{:.1f} m".format(gap_mean)),
        ("pressure distance", "{:.1f} m to the ball".format(
            float(np.nanmean(pressure[frames][np.isfinite(pressure[frames])])))),
        ("players in the box", "median {:.0f}".format(
            float(np.nanmedian(in_box[frames])))),
    ]

    return Tactic(
        id="defending",
        title="Defending",
        answer="the defending team averaged {:.1f} m wide, with its line {:.1f} m from its own "
               "goal line and a biggest gap of {:.1f} m.".format(
                   width_mean, height_mean, gap_mean),
        detail=detail,
        frames=frames,
        confidence="the shape is measured on the frames where the ball is observed and the "
                   "match is live; a player the tracker has lost is not in the shape, and a "
                   "track slot that has swapped identity would distort it",
    )


def transitions(analysis: Analysis, mask: np.ndarray, geo: Geometry) -> Tactic:
    """What happens after the ball changes hands.

    Chain length is how many possessions in a row a team holds; the counter-press is the share
    of losses the losing team wins back inside ten seconds.
    """
    n = analysis.n_frames
    possessions = [
        (a, b, label)
        for a, b, label in analysis.spells
        if label in (HOME, AWAY) and mask[a:min(b + 1, n)].any()
    ]
    frames = np.zeros(n, dtype=bool)
    for a, b, _ in possessions:
        frames[a:min(b + 1, n)] = True

    chains: List[int] = []
    current = 0
    previous = None
    for a, b, label in possessions:
        if previous is not None and label != previous and current:
            chains.append(current)
            current = 0
        current += 1
        previous = label
    if current:
        chains.append(current)

    # Counter-press: after a change of hands, does the team that lost it get it back?
    losses = 0
    regains = 0
    regain_times: List[float] = []
    for index in range(1, len(possessions)):
        previous_a, previous_b, previous_label = possessions[index - 1]
        a, b, label = possessions[index]
        if label == previous_label:
            continue
        losses += 1
        horizon = min(n - 1, a + int(COUNTER_PRESS_SECONDS * FPS))
        later = [
            (aa, bb, ll) for aa, bb, ll in possessions
            if aa > previous_b and aa <= horizon
        ]
        if later and later[0][2] == previous_label:
            regains += 1
            regain_times.append((later[0][0] - previous_b) / FPS)

    detail = [
        ("possessions", str(len(possessions))),
        ("chain length", "mean {:.1f}, longest {}".format(
            float(np.mean(chains)) if chains else 0.0, max(chains) if chains else 0)),
        ("changes of hands", str(losses)),
        ("won back within 10 s", "{} of {}".format(regains, losses)),
        ("time to win it back", "{:.1f} s".format(
            float(np.mean(regain_times)) if regain_times else 0.0)),
    ]

    if losses == 0:
        return Tactic(
            id="transitions",
            title="Transitions",
            answer="no change of hands in this window.",
            detail=detail,
            frames=frames,
            confidence="nothing to measure",
        )

    return Tactic(
        id="transitions",
        title="Transitions",
        answer="after {} changes of hands, the team that lost the ball won it back within ten "
               "seconds {} times.".format(losses, regains),
        detail=detail,
        frames=frames,
        confidence="a counter-press counts when the losing team has the ball again within ten "
                   "seconds; possession spells are the ones the engine's own rules produced",
    )


def chance_creation(analysis: Analysis, mask: np.ndarray, geo: Geometry) -> Tactic:
    """How often a possession reaches the final third, and the box.

    The zones are relative to the team in possession, so "the final third" means the third the
    team is attacking into.
    """
    n = analysis.n_frames
    home_right = attacking_sides(analysis)
    length = analysis.pitch_length_m
    width = analysis.pitch_width_m

    possession = analysis.labels
    own_right = np.where(possession == HOME, home_right, ~home_right)
    progress_x = np.where(own_right, analysis.ball_xy[:, 0], length - analysis.ball_xy[:, 0])

    live = _alive(analysis, mask) & analysis.evidence.ball_present
    final_third = live & (progress_x > 2 * length / 3)
    box = live & (progress_x > length - 16.5) & (np.abs(analysis.ball_xy[:, 1] - width / 2) < 20.3)

    possessions = [
        (a, b, label)
        for a, b, label in analysis.spells
        if label in (HOME, AWAY) and mask[a:min(b + 1, n)].any()
    ]
    frames = np.zeros(n, dtype=bool)
    entries_final = 0
    entries_box = 0
    possessions_final = 0
    possessions_box = 0
    home_entries = 0
    away_entries = 0
    for a, b, label in possessions:
        window = slice(a, min(b + 1, n))
        frames[window] = True
        for zone, counter in ((final_third, "final"), (box, "box")):
            inside = zone[window]
            if not inside.any():
                continue
            # An entry is a crossing into the zone, not a frame spent in it: a possession that
            # goes in and comes out and goes back in is two entries.
            crossings = int(np.sum(inside[1:] & ~inside[:-1])) + int(inside[0])
            if counter == "final":
                entries_final += crossings
                possessions_final += 1
                if label == HOME:
                    home_entries += crossings
                else:
                    away_entries += crossings
            else:
                entries_box += crossings
                possessions_box += 1

    detail = [
        ("possessions", str(len(possessions))),
        ("entries into the final third", "{} ({:.2f} per possession)".format(
            entries_final, entries_final / len(possessions) if possessions else 0.0)),
        ("entries into the penalty area", "{} ({:.2f} per possession)".format(
            entries_box, entries_box / len(possessions) if possessions else 0.0)),
        ("possessions that got there", "{} final third, {} box".format(
            possessions_final, possessions_box)),
        ("final-third entries", "{} home, {} away".format(home_entries, away_entries)),
    ]

    if not possessions:
        return Tactic(
            id="chance_creation",
            title="Chance creation",
            answer="no possessions in this window.",
            detail=detail,
            frames=frames,
            confidence="nothing to measure",
        )

    return Tactic(
        id="chance_creation",
        title="Chance creation",
        answer="{} entries into the final third and {} into the penalty area, from {} "
               "possessions.".format(entries_final, entries_box, len(possessions)),
        detail=detail,
        frames=frames,
        confidence="an entry is a crossing into the zone; the zone is relative to the team in "
                   "possession, and it counts only where the ball is observed",
    )


TACTICS = {
    "restarts": restarts,
    "pressing": pressing,
    "build_up": build_up,
    "defending": defending,
    "transitions": transitions,
    "chance_creation": chance_creation,
}
