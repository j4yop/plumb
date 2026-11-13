"""Tune the pipeline on EXTERNAL data, as the organisers' rules require.

Why this exists
---------------
The clarification email is explicit:

    "If you need to train (or retrain), you MUST use only external data. If your algorithm has
     parameters that need to be tuned, you MUST tune them on external data, never on the
     ground-truth possession data or on the provided video."

So every threshold in ``mtah.config`` has to earn its place on data that is not the provided
game. This script builds that set from **Metrica Sports' own public sample data**
(https://github.com/metrica-sports/sample-data, "please acknowledge the source"), and it is
deliberately the *same formats* as the competition bundle:

* ``Sample_Game_3_tracking.txt`` — FIFA/EPTS tracking, the same shape as the competition ATD.
* ``Sample_Game_3_metadata.xml`` — the same metadata schema.
* ``Sample_Game_3_events.json`` — 3,620 frame-accurate event annotations.

The event stream is what makes it a *possession* ground truth: the team of the most recent
on-ball action owns the ball, and ``BALL OUT`` / ``SET PIECE`` mark the dead-ball stretches. That
gives a frame-by-frame possession label for a match we are allowed to tune on.

The point is not to find a better score on the competition match. It is to answer a question that
matters more: **are the thresholds we shipped the right ones?** If the same values come out of an
external match, they are not a fit to the five public minutes.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mtah.config import Config
from mtah.decide import assign_owners, build_spells
from mtah.evidence import build_evidence
from mtah.match import Match

# --------------------------------------------------------------------------------------------------
# Where the external data lives
# --------------------------------------------------------------------------------------------------

SAMPLE_DIR = os.environ.get(
    "MTAH_SAMPLE_DIR",
    "/private/var/folders/pv/x_b_3fy12z9g3bxv14wl5jv80000gn/T/opencode/sample-data/data/Sample_Game_3",
)

ON_BALL = {"PASS", "CARRY", "SHOT", "CHALLENGE", "RECOVERY"}
DEAD_MARKERS = {"BALL OUT", "SET PIECE"}


def load_events(path: str) -> List[dict]:
    with open(path) as handle:
        return json.load(handle)["data"]


def possession_truth(events: List[dict], n_frames: int) -> Tuple[np.ndarray, np.ndarray]:
    """Frame-by-frame possession and dead-ball labels derived from the event stream.

    The rule a human would apply: the ball belongs to the team of the last thing that touched it,
    until the other team touches it. ``BALL LOST`` ends the possession without giving it to
    anybody; ``BALL OUT`` and ``SET PIECE`` are dead-ball stretches until the next on-ball action.

    Returns ``(labels, dead)`` where labels are 0 home, 1 away, -1 unknown.
    """
    team_index = {}
    for event in events:
        name = event["team"]["name"]
        team_index.setdefault(name, len(team_index))

    labels = np.full(n_frames, -1, dtype=np.int8)
    dead = np.zeros(n_frames, dtype=bool)

    ordered = sorted(events, key=lambda e: (e["start"]["frame"], e["index"]))
    owner = -1
    dead_until = -1
    for event in ordered:
        start = int(event["start"]["frame"]) - 1
        if start < 0 or start >= n_frames:
            continue
        kind = event["type"]["name"]
        team = team_index[event["team"]["name"]]
        if kind in DEAD_MARKERS:
            dead_until = max(dead_until, int(event["end"]["frame"]) - 1)
            owner = -1
            continue
        if kind == "BALL LOST":
            owner = -1
            continue
        if kind in ON_BALL:
            owner = team
            dead_until = -1
        labels[start:] = owner

    # Dead stretches: from the marker until the next on-ball action.
    dead = np.zeros(n_frames, dtype=bool)
    current_dead = False
    for index in range(n_frames):
        if labels[index] == -1 and current_dead:
            dead[index] = True
        if labels[index] != -1:
            current_dead = False
    # Anything before the first event is unknown.
    return labels, dead


def assign_slots_to_teams(
    player_xy: np.ndarray, events: List[dict], player_team: Dict[str, int], config: Config
) -> np.ndarray:
    """Which team does each tracking column belong to, decided by the events.

    The sample game's metadata lists every player who appeared (35) but the tracking has one
    column per player on the pitch (22), so the file order cannot be trusted. The events know
    which player was where at which frame, so each event votes for the column nearest to it.
    A handful of votes per column is enough to settle the side, and the margin is checked.
    """
    n_frames, n_slots = player_xy.shape[0], player_xy.shape[1]
    votes = np.zeros((n_slots, 2), dtype=np.int64)
    for event in events:
        start = event.get("start") or {}
        origin = event.get("from")
        if not origin or origin.get("id") not in player_team:
            continue
        x, y = start.get("x"), start.get("y")
        if x is None or y is None:
            continue
        frame = int(start.get("frame", 0)) - 1
        if not (0 <= frame < n_frames):
            continue
        point = np.array([x * config.pitch_length_m, y * config.pitch_width_m], dtype=np.float32)
        distance = np.linalg.norm(player_xy[frame] - point, axis=1)
        slot = int(np.nanargmin(distance))
        if distance[slot] < 6.0:  # metres: only a close match is a vote
            votes[slot, player_team[origin["id"]]] += 1
    slot_team = votes.argmax(axis=1).astype(np.int8)
    return slot_team


def build_match(sample_dir: str, config: Config) -> Tuple[Match, np.ndarray]:
    """Read the sample game into the same ``Match`` the pipeline consumes."""
    tracking_path = os.path.join(sample_dir, "Sample_Game_3_tracking.txt")
    meta_path = os.path.join(sample_dir, "Sample_Game_3_metadata.xml")
    events_path = os.path.join(sample_dir, "Sample_Game_3_events.json")

    root = ET.parse(meta_path).getroot()
    teams = [team.get("id") for team in root.iter("Team")]
    name_to_index = {team_id: index for index, team_id in enumerate(teams)}
    players = list(root.iter("Player"))
    player_team = {p.get("id"): name_to_index[p.get("teamId")] for p in players}

    n_slots = None
    frames = []
    with open(tracking_path) as handle:
        for line in handle:
            parts = line.strip().split(":")
            if len(parts) != 3:
                continue
            groups = parts[1].split(";")
            if n_slots is None:
                n_slots = len(groups)
            frames.append((int(parts[0]), parts[1], parts[2]))
    n_frames = len(frames)

    player_xy = np.full((n_frames, n_slots, 2), np.nan, dtype=np.float32)
    ball_xy = np.full((n_frames, 2), np.nan, dtype=np.float32)
    for index, (_frame_id, player_text, ball_text) in enumerate(frames):
        for slot, group in enumerate(player_text.split(";")):
            if group[0] == "N":
                continue
            comma = group.find(",")
            second = group.find(",", comma + 1)
            x = float(group[:comma])
            y = float(group[comma + 1:second] if second > 0 else group[comma + 1:])
            player_xy[index, slot, 0] = x * config.pitch_length_m
            player_xy[index, slot, 1] = y * config.pitch_width_m
        ball = ball_text.split(",")
        if ball[0] != "N":
            ball_xy[index, 0] = float(ball[0]) * config.pitch_length_m
            ball_xy[index, 1] = float(ball[1]) * config.pitch_width_m

    events = load_events(events_path)
    slot_team = assign_slots_to_teams(player_xy, events, player_team, config)

    match = Match(
        n_frames=n_frames,
        n_slots=n_slots,
        team_names=("Team A", "Team B"),
        slot_team=slot_team,
        player_xy=player_xy,
        player_speed=np.full((n_frames, n_slots), np.nan, dtype=np.float32),
        ball_xy=ball_xy,
        ball_speed=np.full(n_frames, np.nan, dtype=np.float32),
        set_pieces=[],
    )
    truth, dead = possession_truth(events, n_frames)
    return match, truth


# --------------------------------------------------------------------------------------------------
# Scoring: the same shape as the competition metric, on external data
# --------------------------------------------------------------------------------------------------


def runs_of(labels: np.ndarray) -> List[Tuple[int, int, int]]:
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [labels.size]))
    return [(int(a), int(b), int(labels[a])) for a, b in zip(starts, stops)]


def possession_spells(labels: np.ndarray) -> List[Tuple[int, int, int]]:
    return [(a, b, label) for a, b, label in runs_of(labels) if label in (0, 1)]


def spell_f1(truth: np.ndarray, predicted: np.ndarray, ious=(0.3, 0.4, 0.5, 0.6, 0.7)) -> float:
    """Mean F1 over IoU thresholds, matching the competition's metric in shape."""
    truth_spells = possession_spells(truth)
    predicted_spells = possession_spells(predicted)
    if not truth_spells or not predicted_spells:
        return 0.0

    overlaps = []
    for i, (ta, tb, tc) in enumerate(truth_spells):
        for j, (pa, pb, pc) in enumerate(predicted_spells):
            if pc != tc:
                continue
            intersection = min(tb, pb) - max(ta, pa)
            union = max(tb, pb) - min(ta, pa)
            if intersection > 0:
                overlaps.append((intersection / union, i, j))
    overlaps.sort(key=lambda item: (-item[0], item[1], item[2]))

    scores = []
    for threshold in ious:
        matched_truth = set()
        matched_pred = set()
        for iou, i, j in overlaps:
            if iou < threshold:
                break
            if i in matched_truth or j in matched_pred:
                continue
            matched_truth.add(i)
            matched_pred.add(j)
        true_positive = len(matched_truth)
        precision = true_positive / len(predicted_spells)
        recall = true_positive / len(truth_spells)
        scores.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    return float(np.mean(scores))


def frame_accuracy(truth: np.ndarray, predicted: np.ndarray) -> float:
    known = truth >= 0
    if not known.any():
        return 0.0
    return float(np.mean(predicted[known] == truth[known]))


def run_configuration(match: Match, truth: np.ndarray, config: Config) -> Dict[str, float]:
    evidence = build_evidence(match, config)
    owners, episodes = assign_owners(evidence, config)
    decision = build_spells(owners, evidence, config, episodes=episodes)
    predicted = np.where(decision.labels == 0, 0, np.where(decision.labels == 1, 1, -1))
    alive = truth >= 0
    return {
        "spell_f1": spell_f1(truth, predicted),
        "frame_acc": frame_accuracy(truth, predicted),
        "possessions": len(possession_spells(predicted)),
        "truth_possessions": len(possession_spells(truth)),
        "dead_pct": float(np.mean(decision.labels[alive] == 2)) if alive.any() else 0.0,
    }


def main() -> int:
    if not os.path.isdir(SAMPLE_DIR):
        print("external sample data not found at {}".format(SAMPLE_DIR))
        print("clone it with:  git clone --depth 1 https://github.com/metrica-sports/sample-data.git")
        return 1

    config = Config()
    match, truth = build_match(SAMPLE_DIR, config)
    print("external match: {} frames, {} slots".format(match.n_frames, match.n_slots))
    print("event-derived possession: {} spells, {} frames of live ball".format(
        len(possession_spells(truth)), int((truth >= 0).sum())))
    print()

    # The external reference carries no dead-ball class, so the dead layer is switched off for
    # the comparison: otherwise we would be scoring the two definitions against each other.
    external = Config(**{**config.as_dict(), "dead_detection": False})

    shipped = run_configuration(match, truth, config)
    print("SHIPPED configuration (dead layer ON, for reference)")
    for key, value in shipped.items():
        print("  {:<18} {}".format(key, round(value, 4) if isinstance(value, float) else value))
    print()

    baseline = run_configuration(match, truth, external)
    print("SHIPPED configuration with the dead layer OFF (the comparable setting)")
    for key, value in baseline.items():
        print("  {:<18} {}".format(key, round(value, 4) if isinstance(value, float) else value))
    print()

    grid = {
        "control_radius_m": [1.5, 2.0, 2.5, 3.0, 3.5],
        "handover_margin_m": [0.0, 0.25, 0.5, 1.0],
        "min_control_frames": [5, 12, 25, 50],
        "dead_movers": [0, 1, 2, 4],
        "min_spell_frames": [12, 25, 50],
    }
    print("one-at-a-time sensitivity around the shipped values\n")
    for key, values in grid.items():
        print("  {}".format(key))
        for value in values:
            candidate = Config(**{**external.as_dict(), key: value})
            result = run_configuration(match, truth, candidate)
            marker = "  <- shipped" if value == getattr(external, key) else ""
            print("    {:<8} spellF1 {:.4f}  frameAcc {:.4f}  possessions {}".format(
                str(value), result["spell_f1"], result["frame_acc"], result["possessions"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
