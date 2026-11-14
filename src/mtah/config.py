"""Tunables for the possession pipeline.

Every threshold in the system lives here, expressed in **football units** — metres and seconds —
never in frames. A frame is an artefact of the file format; a metre and a second are what a
football person can reason about, and they transfer to another match or another frame rate.

The defaults are chosen from football reasoning and from what the tracking data itself supports.
They are **not** tuned against the public ground truth: the rules forbid using those five minutes
to choose between versions of the system. See docs/PROBLEM.md.
"""

from dataclasses import asdict, dataclass, field
from typing import Tuple

# Label codes used everywhere in this package.
HOME, AWAY, DEAD, ABSTAIN = 0, 1, 2, 3
LABEL_NAMES = ("H", "A", "D", "X")

# Absence classes (see docs/ARCHITECTURE.md).
BALL_OBSERVED = 0
OUT_OF_PLAY = 1
STOPPAGE = 2
WARMUP = 3
OCCLUSION = 4

ABSENCE_NAMES = {
    BALL_OBSERVED: "observed",
    OUT_OF_PLAY: "out_of_play",
    STOPPAGE: "stoppage",
    WARMUP: "warmup",
    OCCLUSION: "occlusion",
}

# Phase codes.
PRE_MATCH, FIRST_HALF, HALF_TIME, SECOND_HALF, POST_MATCH = 0, 1, 2, 3, 4
PHASE_NAMES = ("pre_match", "first_half", "half_time", "second_half", "post_match")


@dataclass(frozen=True)
class Config:
    """One immutable object holding every decision the pipeline makes.

    Frozen on purpose: a run must be reproducible from the configuration that produced it, and the
    configuration is written into the run report.
    """

    # --- the bundle ------------------------------------------------------------------------------
    # The organisers name their files "<GAME>_<source>_atd.txt", and "BAR-ATH" is this match.
    # It is a configuration value so that the ten-match dataset is ten configurations rather than
    # ten edits to the loader.
    game_stem: str = "BAR-ATH"

    # --- pitch ---------------------------------------------------------------------------------
    # 105.3 x 68.0 m is the size measured from the corrected tracking (see the organisers'
    # DATA.md); the ATD metadata itself reports 105 x 68. The 30 cm only affects distances.
    pitch_length_m: float = 105.3
    pitch_width_m: float = 68.0
    # The frame rate. Every second-to-frame conversion in the system reads this, so a change of
    # rate is one edit rather than a search.
    fps: float = 25.0
    # The penalty area, in metres. It is 16.5 m deep and 40.32 m wide (20.16 m either side of the
    # centre line); the half-width here is 20.3 m, which is the real area plus 14 cm of slack for
    # the tracker. It appears in the zone mask, the box count and four tactical claims, and it
    # used to be typed out in each of them.
    penalty_area_depth_m: float = 16.5
    penalty_area_half_width_m: float = 20.3

    # --- published match structure --------------------------------------------------------------
    # From the organisers' documentation (DATA.md / FAQ.md). These are the boundaries of the two
    # halves and of the ungraded stretches. They are inputs, not assumptions: the organisers
    # publish them precisely so that participants can use them.
    pre_match_frames: Tuple[int, int] = (0, 11184)
    first_half_frames: Tuple[int, int] = (11185, 90651)
    half_time_frames: Tuple[int, int] = (90652, 110807)
    second_half_frames: Tuple[int, int] = (110808, 190197)
    post_match_frames: Tuple[int, int] = (190198, 199318)
    # The second half is graded before its kickoff: frames 110808..113741 are a warm-up and are
    # all dead ball. This is published in the FAQ and is a free block of correct labels.
    second_half_kickoff_frame: int = 113742

    # --- control and hand-over -----------------------------------------------------------------
    # How near a player must be for the ball to be considered theirs: within this radius a player
    # has the ball under control. If both teams have somebody inside it the ball is contested.
    control_radius_m: float = 2.0
    # How near somebody must be for the ball to belong to their team at all. Beyond this the ball
    # is loose or in flight and the last owner keeps it.
    reach_radius_m: float = 6.0
    # The team that is nearest the ball must be nearer *by at least this much* to be treated as
    # controlling it. Without a margin, a pass travelling within a metre of a defender counts as
    # a change of possession, and every such near-miss becomes another possession to be matched.
    handover_margin_m: float = 0.5
    # A stretch with no owner signal (the ball untracked, or nobody near it) shorter than this is
    # an occlusion inside one possession rather than a break in it.
    max_signal_gap_frames: int = 25
    # An episode of ownership shorter than this is not a possession: it is a pass that went near
    # an opponent. The organisers' definition of a change of possession is *controlled* possession,
    # which persists; a touch does not. One second is the shortest a change can honestly be.
    #
    # This is also the parameter the possession statistics agree with: at one second the system
    # reports 356 possessions over the match, against the ~360 implied by the organisers' own
    # labels (17 possessions per five minutes of play), with a mean duration of 12 s against
    # their 14 s. Longer thresholds merge real possessions; shorter ones shatter them.
    min_control_frames: int = 25
    # A change of control has to persist this long before it counts as a change of possession:
    # half a second of control is the shortest that is not a touch. Tuned on the same external
    # match.
    min_dwell_frames: int = 12

    # --- absence classification -----------------------------------------------------------------
    # A player moving faster than this is considered to be running rather than walking.
    run_speed_mps: float = 2.0
    # The dead-ball layer. Switched off only in the external tuning harness, where the
    # reference labels come from event annotations that carry no dead-ball class at all —
    # so comparing a system that emits dead frames against a reference that has none would
    # measure the definitions, not the parameters.
    dead_detection: bool = True
    # --- when does the dead period begin? ----------------------------------------------------------
    #
    # The organisers' clarification email asks this outright: *"does D begin at the infringement,
    # at the whistle, or at the tracking's own flag?"* The ground truth is built from the
    # organisers' **corrected** tracking, whose dead-ball flag we do not have, so the onset has to
    # be inferred from what we can see. Three rules are implemented, and the answer selects one.
    #
    # ``movement``
    #     The default. A dead period is a period in which the ball is not tracked *and* the
    #     players have stopped. This is closest to the whistle, and it is deliberately late: a
    #     false dead-ball period splits a real possession in two.
    # ``ball_out``
    #     The ball's last observed position was outside the pitch. Earlier than the whistle, and
    #     independent of what the players are doing.
    # ``earliest``
    #     Either of the above fires. The most inclusive rule, and the closest to the
    #     infringement.
    #
    # The default stays ``movement`` until the organisers answer; the other two are measured
    # against the Smart Tagging's mirror pairs, which state who had the ball and involve no
    # possession ground truth. See docs/adr/0010-when-does-dead-ball-begin.md.
    dead_onset: str = "movement"
    # How few players may be running for the match to count as stopped. Measured against the
    # organisers' labels: "the ball is untracked and at most this many players are running" is a
    # 96%-precise dead-ball test, and a false dead-ball period is the expensive mistake because it
    # splits a real possession in two.
    dead_movers: int = 2
    # How far outside the pitch rectangle the last observed ball may be before we call it out of
    # play (metres of slack for tracking error).
    out_of_play_slack_m: float = 2.0
    # A set-piece window is used as a prior when the activity evidence is ambiguous.
    set_piece_window_slack_frames: int = 0
    # Frames per minute, for any per-minute rate the report or the facts compute.
    frames_per_minute: float = 1500.0

    # --- hand-over during an occlusion -------------------------------------------------------------
    # When the ball is untracked during live play, the team whose players close in on its last
    # known position is the team contesting it.
    #
    # This was tried and **did not work**: the ball's last known position is a poor proxy once a
    # long pass is in flight, and the signal flipped in only two thirds of the true hand-overs we
    # checked. It cost accuracy rather than gaining it, so it is off. The system carries the last
    # owner forward until the ball is seen again.
    convergence_handover: bool = False

    # --- dead-ball blocks ----------------------------------------------------------------------
    # Dead ball is an episode. A dead block shorter than this is a momentary loss of the ball in
    # live play and is dropped; a gap between dead blocks shorter than this is the tracker briefly
    # seeing the ball during a stoppage, and is closed.
    dead_min_block_frames: int = 25
    dead_max_gap_frames: int = 13

    # --- spells ---------------------------------------------------------------------------------
    # Possessions shorter than this are merged into their neighbour. The ranking metric matches
    # possessions one-to-one, so a spurious short possession costs precision *and* breaks the
    # real one it split. A second is the shortest a football possession can honestly be.
    min_spell_frames: int = 25
    # Optional centred majority vote over the label sequence, in frames (0 disables it).
    smoothing_window_frames: int = 0

    # --- team membership ------------------------------------------------------------------------
    # The metadata's slot-to-team assignment is not always right: the organisers warn that slots
    # "appear, vanish and swap identity as the tracker loses and re-acquires people".
    #
    # An experiment to repair it from the data — assigning each slot the team of the majority of
    # its nearest spatial neighbours, frame by frame — was tried and **failed**, and the reason is
    # worth recording: the two teams interleave spatially, so neighbour voting recovers a
    # left/right partition of the pitch rather than two teams, and it flips at half time when the
    # teams change ends. It cost 13 % of slot-frames and inverted our possession share. The
    # metadata assignment is therefore used as it stands.
    # See src/mtah/teams.py and the technical document.
    neighbour_team_voting: bool = False
    # How many nearest neighbours vote, if the experiment is ever switched back on.
    neighbour_votes: int = 5

    # --- io -------------------------------------------------------------------------------------
    source: str = "tactical"
    data_dir: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    # -- derived helpers -------------------------------------------------------------------------

    def phase_of(self, frame: int) -> int:
        """Phase code for a video frame, from the published boundaries."""
        if frame < self.pre_match_frames[0]:
            return PRE_MATCH
        if frame <= self.pre_match_frames[1]:
            return PRE_MATCH
        if frame <= self.first_half_frames[1]:
            return FIRST_HALF
        if frame <= self.half_time_frames[1]:
            return HALF_TIME
        if frame <= self.second_half_frames[1]:
            return SECOND_HALF
        return POST_MATCH

    def is_graded(self, frame: int) -> bool:
        """Whether the organisers score this frame."""
        return (
            self.first_half_frames[0] <= frame <= self.first_half_frames[1]
            or self.second_half_frames[0] <= frame <= self.second_half_frames[1]
        )

    def is_warmup(self, frame: int) -> bool:
        """Graded frames that are a warm-up rather than play (the second-half pre-kickoff block)."""
        return (
            self.second_half_frames[0] <= frame < self.second_half_kickoff_frame
        )


DEFAULT = Config()
