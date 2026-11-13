"""Tune and check the pipeline on EXTERNAL data, across three independent matches.

Why this exists
---------------
The clarification email is explicit:

    "If you need to train (or retrain), you MUST use only external data. If your algorithm has
     parameters that need to be tuned, you MUST tune them on external data, never on the
     ground-truth possession data or on the provided video."

So every threshold in ``mtah.config`` has to earn its place on data that is not the provided
game. This harness builds that set from **Metrica Sports' own public sample data**
(https://github.com/metrica-sports/sample-data — "if you use it for anything public, please
acknowledge the source"), which is:

* ``Sample_Game_3`` — FIFA/EPTS tracking, the same shape as the competition ATD, with 3,620
  frame-accurate events in JSON;
* ``Sample_Game_1`` and ``Sample_Game_2`` — Metrica's CSV format, with 1,745 and 1,935 events.

All three carry an event stream, and the event stream is what makes a *possession* truth: the
team of the most recent on-ball action owns the ball, and ``BALL OUT`` / ``SET PIECE`` mark the
dead stretches.

Three games, not one, because the question that matters is not "what wins on this match" but
**"is the value we shipped the value the geometry supports, on more than one match?"**

What this harness does *not* do
-------------------------------
It does not use the possession labels of the provided match, and it does not use the video. The
only thing it touches is external data.

Two pieces of care were needed to make the comparison honest:

* **The hunting of the slot→team map.** Game 3's metadata lists 35 players but the tracking has
  22 on-pitch columns, so the file order cannot be trusted. Each event votes for the column
  nearest to it; the margin is tens of votes per column. Games 1 and 2 do not need this: their
  tracking files are already split by team.
* **Each match's own half boundaries.** The competition match's windows are meaningless on
  another match — using them would mark three thousand mid-match frames as a warm-up. Each
  game's boundaries are read from its own metadata (game 3) or its own ``Period`` column
  (games 1 and 2).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mtah.config import AWAY, DEAD, HOME, Config
from mtah.decide import assign_owners, build_spells
from mtah.evidence import build_evidence
from mtah.match import Match

# --------------------------------------------------------------------------------------------------
# Where the external data lives
# --------------------------------------------------------------------------------------------------

SAMPLE_ROOT = os.environ.get(
    "MTAH_SAMPLE_ROOT",
    "/private/var/folders/pv/x_b_3fy12z9g3bxv14wl5jv80000gn/T/opencode/sample-data/data",
)

ON_BALL = {"PASS", "CARRY", "SHOT", "CHALLENGE", "RECOVERY"}
DEAD_MARKERS = {"BALL OUT", "SET PIECE"}

GAMES = {1: "Sample_Game_1", 2: "Sample_Game_2", 3: "Sample_Game_3"}


# --------------------------------------------------------------------------------------------------
# Possession truth from an event stream (the same rule for all three games)
# --------------------------------------------------------------------------------------------------


def possession_truth(events: List[dict], n_frames: int, team_index: Dict[str, int]) -> np.ndarray:
    """Frame-by-frame possession from the event stream: 0 home, 1 away, -1 unknown.

    The rule a human would apply: the ball belongs to the team of the last thing that touched it,
    until the other team touches it. ``BALL LOST`` ends the possession without giving it to
    anybody; ``BALL OUT`` and ``SET PIECE`` are dead stretches.

    ``team_index`` must be the **same** mapping the tracking uses, or the truth and the labels
    are inverted and the score is worse than chance. That is not a hypothetical: it is what
    happened the first time these two games were read.
    """
    labels = np.full(n_frames, -1, dtype=np.int8)
    ordered = sorted(events, key=lambda e: (e["start"], e["index"]))
    owner = -1
    for event in ordered:
        start = int(event["start"])
        if start < 0 or start >= n_frames:
            continue
        kind = event["type"]
        if kind in DEAD_MARKERS:
            owner = -1
            continue
        if kind == "BALL LOST":
            owner = -1
            continue
        if kind in ON_BALL:
            owner = team_index[event["team"]]
        labels[start:] = owner
    return labels


def epts_events(path: str) -> List[dict]:
    """Game 3's JSON events in the common shape."""
    with open(path) as handle:
        raw = json.load(handle)["data"]
    out = []
    for index, event in enumerate(raw):
        start = event.get("start") or {}
        point = None
        if start.get("x") is not None and start.get("y") is not None:
            point = (float(start["x"]), float(start["y"]))
        out.append({
            "index": index,
            "start": int(event["start"]["frame"]) - 1,
            "end": int(event["end"]["frame"]) - 1,
            "type": event["type"]["name"],
            "team": event["team"]["name"],
            "from": event.get("from"),
            "start_point": point,
        })
    return out


def csv_events(path: str) -> List[dict]:
    """Games 1 and 2's CSV events in the common shape.

    The team is ``Home``/``Away`` in the file; it is mapped to the same names the tracking files
    use so that the truth and the slots agree.
    """
    out = []
    with open(path, newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            out.append({
                "index": index,
                "start": int(row["Start Frame"]) - 1,
                "end": int(row["End Frame"]) - 1,
                "type": row["Type"].strip(),
                "team": row["Team"].strip(),
            })
    return out


# --------------------------------------------------------------------------------------------------
# Reading the tracking
# --------------------------------------------------------------------------------------------------


def read_epts(sample_dir: str, config: Config) -> Tuple[Match, List[dict], dict]:
    """Sample_Game_3: the FIFA/EPTS format, the same shape as the competition bundle."""
    tracking_path = os.path.join(sample_dir, "Sample_Game_3_tracking.txt")
    meta_path = os.path.join(sample_dir, "Sample_Game_3_metadata.xml")

    root = ET.parse(meta_path).getroot()
    params = {
        item.findtext("Name"): (item.findtext("Value") or "").strip()
        for item in root.iter("ProviderParameter")
    }
    teams = [team.get("id") for team in root.iter("Team")]
    name_to_index = {team_id: index for index, team_id in enumerate(teams)}
    players = list(root.iter("Player"))
    player_team = {p.get("id"): name_to_index[p.get("teamId")] for p in players}

    frames = []
    n_slots = None
    with open(tracking_path) as handle:
        for line in handle:
            parts = line.strip().split(":")
            if len(parts) != 3:
                continue
            groups = parts[1].split(";")
            if n_slots is None:
                n_slots = len(groups)
            frames.append((parts[1], parts[2]))
    n_frames = len(frames)

    player_xy = np.full((n_frames, n_slots, 2), np.nan, dtype=np.float32)
    ball_xy = np.full((n_frames, 2), np.nan, dtype=np.float32)
    for index, (player_text, ball_text) in enumerate(frames):
        for slot, group in enumerate(player_text.split(";")):
            if group[0] == "N":
                continue
            comma = group.find(",")
            second = group.find(",", comma + 1)
            player_xy[index, slot, 0] = float(group[:comma]) * config.pitch_length_m
            y_text = group[comma + 1:second] if second > 0 else group[comma + 1:]
            player_xy[index, slot, 1] = float(y_text) * config.pitch_width_m
        ball = ball_text.split(",")
        if ball[0] != "N":
            ball_xy[index, 0] = float(ball[0]) * config.pitch_length_m
            ball_xy[index, 1] = float(ball[1]) * config.pitch_width_m

    events = epts_events(os.path.join(sample_dir, "Sample_Game_3_events.json"))
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
    halves = {
        "first": (int(params["first_half_start"]) - 1, int(params["first_half_end"]) - 1),
        "second": (int(params["second_half_start"]) - 1, int(params["second_half_end"]) - 1),
    }
    # The event stream names the teams, the tracking numbers them; the metadata's order is the
    # tracking's order, so map the names onto it.
    names = [team.findtext("Name") for team in root.iter("Team")]
    team_index = {name: index for index, name in enumerate(names)}
    return match, events, halves, team_index


def assign_slots_to_teams(
    player_xy: np.ndarray, events: List[dict], player_team: Dict[str, int], config: Config
) -> np.ndarray:
    """Which team each tracking column belongs to, decided by the events.

    The metadata lists every player who appeared (35) but the tracking has one column per player
    on the pitch (22), so the file order cannot be trusted. Each event votes for the column
    nearest to it, using the player it names. A handful of votes per column settles the side, and
    the margins come out in the tens.
    """
    n_frames, n_slots = player_xy.shape[0], player_xy.shape[1]
    votes = np.zeros((n_slots, 2), dtype=np.int64)
    for event in events:
        origin = event.get("from")
        if not origin or origin.get("id") not in player_team:
            continue
        start = event.get("start_point")
        if start is None:
            continue
        x, y = start
        frame = int(event["start"])
        if not (0 <= frame < n_frames):
            continue
        point = np.array([x * config.pitch_length_m, y * config.pitch_width_m], dtype=np.float32)
        distance = np.linalg.norm(player_xy[frame] - point, axis=1)
        slot = int(np.nanargmin(distance))
        if distance[slot] < 6.0:
            votes[slot, player_team[origin["id"]]] += 1
    return votes.argmax(axis=1).astype(np.int8)


def read_csv(sample_dir: str, game: int, config: Config) -> Tuple[Match, List[dict], dict]:
    """Games 1 and 2: Metrica's CSV format.

    The layout is three metadata columns, then one **two-column** group (x, y) per player, then
    the ball. The team of each group is in the first header row, the player id in the second, so
    no voting is needed here — the files are already split by team.
    """
    stem = "Sample_Game_{}".format(game)
    home_rows = _read_tracking_csv(os.path.join(sample_dir, stem + "_RawTrackingData_Home_Team.csv"))
    away_rows = _read_tracking_csv(os.path.join(sample_dir, stem + "_RawTrackingData_Away_Team.csv"))

    n_home = (len(home_rows["header"]) - 3) // 2 - 1  # minus the ball group
    n_away = (len(away_rows["header"]) - 3) // 2 - 1
    n_slots = n_home + n_away

    n_frames = max(len(home_rows["data"]), len(away_rows["data"]))
    player_xy = np.full((n_frames, n_slots, 2), np.nan, dtype=np.float32)
    ball_xy = np.full((n_frames, 2), np.nan, dtype=np.float32)
    period = np.zeros(n_frames, dtype=np.int8)

    for index, row in enumerate(home_rows["data"]):
        period[index] = int(row[0])
        for slot in range(n_home):
            x, y = row[3 + 2 * slot], row[3 + 2 * slot + 1]
            if x != "NaN":
                player_xy[index, slot, 0] = float(x) * config.pitch_length_m
                player_xy[index, slot, 1] = float(y) * config.pitch_width_m
        bx, by = row[-2], row[-1]
        if bx != "NaN":
            ball_xy[index, 0] = float(bx) * config.pitch_length_m
            ball_xy[index, 1] = float(by) * config.pitch_width_m
    for index, row in enumerate(away_rows["data"]):
        if index >= n_frames:
            break
        for slot in range(n_away):
            x, y = row[3 + 2 * slot], row[3 + 2 * slot + 1]
            if x != "NaN":
                player_xy[index, n_home + slot, 0] = float(x) * config.pitch_length_m
                player_xy[index, n_home + slot, 1] = float(y) * config.pitch_width_m

    slot_team = np.array([0] * n_home + [1] * n_away, dtype=np.int8)
    events = csv_events(os.path.join(sample_dir, stem + "_RawEventsData.csv"))
    second = np.flatnonzero(period == 2)
    halves = {
        "first": (0, int(second[0]) - 1 if second.size else n_frames - 1),
        "second": (int(second[0]) if second.size else n_frames, n_frames - 1),
    }
    match = Match(
        n_frames=n_frames,
        n_slots=n_slots,
        team_names=("Home", "Away"),
        slot_team=slot_team,
        player_xy=player_xy,
        player_speed=np.full((n_frames, n_slots), np.nan, dtype=np.float32),
        ball_xy=ball_xy,
        ball_speed=np.full(n_frames, np.nan, dtype=np.float32),
        set_pieces=[],
    )
    # Slots 0..n_home-1 come from the home file, so the mapping is fixed here, not inferred.
    return match, events, halves, {"Home": 0, "Away": 1}


def _read_tracking_csv(path: str) -> dict:
    with open(path, newline="") as handle:
        rows = list(csv.reader(handle))
    return {"header": rows[2], "data": rows[3:]}


def config_for(halves: dict, n_frames: int, base: Config) -> Config:
    """A configuration carrying this match's own windows, not another match's."""
    first_start, first_end = halves["first"]
    second_start, second_end = halves["second"]
    return replace(
        base,
        pre_match_frames=(0, max(0, first_start - 1)),
        first_half_frames=(first_start, first_end),
        half_time_frames=(first_end + 1, max(first_end + 1, second_start - 1)),
        second_half_frames=(second_start, second_end),
        post_match_frames=(second_end + 1, max(second_end + 1, n_frames - 1)),
        second_half_kickoff_frame=second_start,
    )


def load_game(game: int, base: Config) -> Tuple[Match, np.ndarray, Config]:
    """One external match, its event-derived truth, and a configuration for it."""
    sample_dir = os.path.join(SAMPLE_ROOT, GAMES[game])
    if not os.path.isdir(sample_dir):
        raise FileNotFoundError(sample_dir)
    if game == 3:
        match, events, halves, team_index = read_epts(sample_dir, base)
    else:
        match, events, halves, team_index = read_csv(sample_dir, game, base)
    truth = possession_truth(events, match.n_frames, team_index)
    return match, truth, config_for(halves, match.n_frames, base)


# --------------------------------------------------------------------------------------------------
# Scoring: the same shape as the competition metric, on external data
# --------------------------------------------------------------------------------------------------


def runs_of(labels: np.ndarray) -> List[Tuple[int, int, int]]:
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate(([0], change))
    stops = np.concatenate((change, [labels.size]))
    return [(int(a), int(b), int(labels[a])) for a, b in zip(starts, stops)]


def possession_spells(labels: np.ndarray) -> List[Tuple[int, int, int]]:
    return [(a, b, label) for a, b, label in runs_of(labels) if label in (HOME, AWAY)]


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
    return {
        "spell_f1": spell_f1(truth, predicted),
        "frame_acc": frame_accuracy(truth, predicted),
        "possessions": len(possession_spells(predicted)),
        "truth_possessions": len(possession_spells(truth)),
    }


# --------------------------------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv or sys.argv[1:]
    games = [int(g) for g in argv] if argv else [1, 2, 3]

    base = Config()
    # The external references carry no dead-ball class, so the dead layer is switched off for the
    # comparison: otherwise we would be scoring two definitions against each other.
    external = replace(base, dead_detection=False)

    loaded = []
    for game in games:
        try:
            match, truth, config = load_game(game, base)
        except FileNotFoundError as error:
            print("game {}: not found at {}".format(game, error))
            continue
        loaded.append((game, match, truth, config))
        print("game {}: {:,} frames, {} slots, {} truth possessions".format(
            game, match.n_frames, match.n_slots, len(possession_spells(truth))))

    if not loaded:
        print("\nNo external data. Clone it with:")
        print("  git clone --depth 1 https://github.com/metrica-sports/sample-data.git")
        return 1

    print()
    print("SHIPPED configuration, each match with its own windows")
    print("  {:<6} {:>9} {:>9} {:>12} {:>12}".format(
        "game", "spellF1", "frameAcc", "possessions", "truth"))
    results = []
    for game, match, truth, config in loaded:
        windows = {
            k: getattr(config, k) for k in (
                "pre_match_frames", "first_half_frames", "half_time_frames",
                "second_half_frames", "post_match_frames", "second_half_kickoff_frame",
            )
        }
        result = run_configuration(match, truth, replace(external, **windows))
        results.append((game, result))
        print("  {:<6} {:>9.4f} {:>9.4f} {:>12} {:>12}".format(
            game, result["spell_f1"], result["frame_acc"],
            result["possessions"], result["truth_possessions"]))

    print()
    print("one-at-a-time sensitivity, summed over the games (the value has to hold on all of them)")
    grid = {
        "control_radius_m": [1.5, 2.0, 2.5, 3.0, 3.5],
        "min_control_frames": [5, 12, 25, 50],
        "min_dwell_frames": [5, 12, 25],
        "handover_margin_m": [0.0, 0.25, 0.5, 1.0],
    }
    for key, values in grid.items():
        print("  {}".format(key))
        for value in values:
            scores = []
            for game, match, truth, config in loaded:
                windows = {
                    k: getattr(config, k) for k in (
                        "pre_match_frames", "first_half_frames", "half_time_frames",
                        "second_half_frames", "post_match_frames", "second_half_kickoff_frame",
                    )
                }
                candidate = replace(external, **{key: value}, **windows)
                scores.append(run_configuration(match, truth, candidate)["spell_f1"])
            marker = "  <- shipped" if value == getattr(base, key) else ""
            print("    {:<7} mean {:.4f}   {}".format(
                str(value), float(np.mean(scores)),
                "  ".join("{:.4f}".format(s) for s in scores) + marker))
    return 0


if __name__ == "__main__":
    sys.exit(main())
