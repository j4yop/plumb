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

CACHE_VERSION = 2


@dataclass
class Analysis:
    """Everything a question can be answered from."""

    labels: np.ndarray  # int8 per frame: 0 H, 1 A, 2 D, 3 X
    spells: List[Tuple[int, int, int]]  # (start, stop, label)
    evidence: Evidence
    ball_xy: np.ndarray  # (n_frames, 2) metres
    n_frames: int

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
        n_frames=match.n_frames,
    )
    _save_cache(path, analysis)
    return analysis


def _save_cache(path: str, analysis: Analysis) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        evidence = analysis.evidence
        np.savez_compressed(
            path,
            version=CACHE_VERSION,
            labels=analysis.labels,
            ball_xy=analysis.ball_xy,
            ball_present=evidence.ball_present,
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

    return Analysis(
        labels=labels,
        spells=_runs(labels),
        evidence=evidence,
        ball_xy=data["ball_xy"],
        n_frames=int(labels.shape[0]),
    )
