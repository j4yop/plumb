"""Run the possession engine once and keep the result in memory.

The CLI asks questions about a match; answering them needs the per-frame labels and the evidence
behind them. Running the whole pipeline for every question would be wasteful, so the analysis is
cached to a single ``.npz`` and reloaded.

The cache is a convenience, never a source of truth: if it is missing or stale, the pipeline runs
again.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from mtah.config import Config
from mtah.decide import assign_owners, build_spells
from mtah.evidence import Evidence, build_evidence
from mtah.match import Match, load_match

CACHE_VERSION = 4


@dataclass
class Analysis:
    """Everything a question can be answered from."""

    labels: np.ndarray  # int8 per frame: 0 H, 1 A, 2 D, 3 X
    spells: List[Tuple[int, int, int]]  # (start, stop, label)
    evidence: Evidence
    ball_xy: np.ndarray  # (n_frames, 2) metres
    player_xy: np.ndarray  # (n_frames, n_slots, 2) metres
    player_speed: np.ndarray  # (n_frames, n_slots) m/s
    slot_team: np.ndarray  # (n_slots,) 0 home, 1 away
    n_frames: int
    teams: np.ndarray = None  # (n_frames, n_slots) int8: the team each slot is on, per frame
    set_pieces: List[Tuple[int, int, str]] = None  # (start, stop, kind) from Smart Tagging
    phases: List = None  # the full Smart Tagging annotation (mtah.match.Phase records)
    pitch_length_m: float = 105.3
    pitch_width_m: float = 68.0

    def __post_init__(self):
        if self.teams is None:
            self.teams = np.broadcast_to(
                self.slot_team, (self.n_frames, self.slot_team.shape[0])
            ).astype(np.int8)
        if self.set_pieces is None:
            self.set_pieces = []
        if self.phases is None:
            self.phases = []
        self._coverage = None
        self._geometry = None

    # -- the derived layers -----------------------------------------------------------------------

    def coverage(self):
        """The reliability engine, built once and kept.

        Local imports, because the derived layers import this module.
        """
        if self._coverage is None:
            from .coverage import build_coverage

            self._coverage = build_coverage(self)
        return self._coverage

    def geometry(self):
        """The ball-to-player distances every aspect needs, built once and kept."""
        if self._geometry is None:
            from .tactics import geometry

            self._geometry = geometry(self)
        return self._geometry

    def window(self, name: str = "all") -> Tuple[int, int]:
        """The video-frame range of a named window."""
        graded = self.evidence.graded
        if name in ("all", "match"):
            return 0, self.n_frames - 1
        if name == "first-half":
            return 11185, 90651
        if name == "second-half":
            return 110808, 190197
        if name == "halftime":
            return 90652, 110807
        # Fall back to the graded frames.
        indices = np.flatnonzero(graded)
        return (int(indices[0]), int(indices[-1])) if indices.size else (0, self.n_frames - 1)


def _cache_path(config: Config) -> str:
    root = os.environ.get("PLUMB_CACHE_DIR") or "artifacts"
    return os.path.join(root, "analysis.npz")


def analyse(config: Config, use_cache: bool = True) -> Analysis:
    """Load the match, decide the possession of every frame, and return the result."""
    path = _cache_path(config)
    if use_cache and os.path.isfile(path):
        cached = _load_cache(path, config)
        if cached is not None:
            return cached

    match = load_match(config)
    evidence = build_evidence(match, config)
    owners, episodes = assign_owners(evidence, config)
    decision = build_spells(owners, evidence, config, episodes=episodes)

    analysis = Analysis(
        labels=decision.labels,
        spells=decision.spells,
        evidence=evidence,
        ball_xy=match.ball_xy,
        player_xy=match.player_xy,
        player_speed=match.player_speed,
        slot_team=match.slot_team,
        n_frames=match.n_frames,
        set_pieces=list(match.set_pieces),
        phases=list(match.phases),
        pitch_length_m=config.pitch_length_m,
        pitch_width_m=config.pitch_width_m,
    )
    _save_cache(path, analysis)
    return analysis


def _save_cache(path: str, analysis: Analysis) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        evidence = analysis.evidence
        starts = np.asarray([w[0] for w in analysis.set_pieces], dtype=np.int32)
        stops = np.asarray([w[1] for w in analysis.set_pieces], dtype=np.int32)
        kinds = np.asarray([w[2] for w in analysis.set_pieces], dtype="U40")
        phase_start = np.asarray([p.start for p in analysis.phases], dtype=np.int32)
        phase_end = np.asarray([p.end for p in analysis.phases], dtype=np.int32)
        phase_code = np.asarray([p.code for p in analysis.phases], dtype="U40")
        phase_team = np.asarray([p.team for p in analysis.phases], dtype="U40")
        phase_kind = np.asarray([p.kind for p in analysis.phases], dtype="U40")
        phase_half = np.asarray([p.half for p in analysis.phases], dtype="U40")
        phase_extra = np.asarray(
            ["\u0000".join("{}={}".format(k, v) for k, v in sorted(p.labels.items()))
             for p in analysis.phases],
            dtype="U400",
        )
        np.savez_compressed(
            path,
            version=CACHE_VERSION,
            labels=analysis.labels,
            ball_xy=analysis.ball_xy,
            ball_present=evidence.ball_present,
            player_xy=analysis.player_xy,
            player_speed=analysis.player_speed,
            slot_team=analysis.slot_team,
            set_piece_start=starts,
            set_piece_stop=stops,
            set_piece_kind=kinds,
            phase_start=phase_start,
            phase_end=phase_end,
            phase_code=phase_code,
            phase_team=phase_team,
            phase_kind=phase_kind,
            phase_half=phase_half,
            phase_extra=phase_extra,
            graded=evidence.graded,
            phase=evidence.phase,
            warmup=evidence.warmup,
            set_piece=evidence.set_piece,
            d_home=evidence.d_home,
            d_away=evidence.d_away,
            activity=evidence.activity,
            moving_players=evidence.moving_players,
            absence_class=evidence.absence_class,
            players_home=evidence.players_home,
            players_away=evidence.players_away,
        )
    except OSError:
        pass  # A missing cache is not an error; the analysis is already in memory.


def _load_cache(path: str, config: Config) -> Analysis:
    try:
        data = np.load(path, allow_pickle=False)
    except (OSError, ValueError):
        return None
    if int(data["version"]) != CACHE_VERSION:
        return None

    labels = data["labels"]
    evidence = Evidence(
        n_frames=int(labels.shape[0]),
        ball_present=data["ball_present"],
        ball_speed=np.full(labels.shape[0], np.nan, dtype=np.float32),
        ball_out_of_play=np.zeros(labels.shape[0], dtype=bool),
        d_home=data["d_home"],
        d_away=data["d_away"],
        near_team=np.full(labels.shape[0], -1, dtype=np.int8),
        near_dist=np.minimum(data["d_home"], data["d_away"]),
        players_home=data["players_home"],
        players_away=data["players_away"],
        activity=data["activity"],
        moving_players=data["moving_players"],
        phase=data["phase"],
        graded=data["graded"],
        warmup=data["warmup"],
        absence_class=data["absence_class"],
        set_piece=data["set_piece"],
    )
    from mtah.decide import _runs  # local import: internal helper

    starts = data["set_piece_start"]
    stops = data["set_piece_stop"]
    kinds = data["set_piece_kind"]
    set_pieces = [
        (int(a), int(b), str(k))
        for a, b, k in zip(starts, stops, kinds)
    ]

    from mtah.match import Phase

    def _labels(blob: str) -> dict:
        out = {}
        for pair in str(blob).split("\u0000"):
            if "=" in pair:
                name, _, value = pair.partition("=")
                out[name] = value
        return out

    phases = [
        Phase(
            start=int(a),
            end=int(b),
            code=str(c),
            team=str(t),
            kind=str(k),
            half=str(h),
            labels=_labels(x),
        )
        for a, b, c, t, k, h, x in zip(
            data["phase_start"], data["phase_end"], data["phase_code"],
            data["phase_team"], data["phase_kind"], data["phase_half"],
            data["phase_extra"],
        )
    ]

    return Analysis(
        labels=labels,
        spells=_runs(labels),
        evidence=evidence,
        ball_xy=data["ball_xy"],
        player_xy=data["player_xy"],
        player_speed=data["player_speed"],
        slot_team=data["slot_team"],
        n_frames=int(labels.shape[0]),
        set_pieces=set_pieces,
        phases=phases,
        pitch_length_m=config.pitch_length_m,
        pitch_width_m=config.pitch_width_m,
    )
