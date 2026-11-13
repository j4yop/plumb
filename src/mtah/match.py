"""Load one match: tracking, team provenance, set pieces.

This is the deep module at the loading seam. Its interface is one function — :func:`load_match` —
and behind it live four things that would otherwise leak into every caller: the FIFA/EPTS metadata
parse, the track-slot-to-team mapping, the streaming of a 187 MB raw tracking file, and the
conversion from normalised pitch coordinates to metres.

Nothing downstream ever sees a file handle, an XML element or a normalised coordinate.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

from .config import Config

# --------------------------------------------------------------------------------------------------
# Public shape of the loaded match
# --------------------------------------------------------------------------------------------------


@dataclass
class Match:
    """Everything we know about one recording, already in metres and video-frame indices.

    Attributes
    ----------
    n_frames:
        Number of video frames. The tactical recording has 199,319.
    n_slots:
        Number of track slots (46 tactical, 51 broadcast). A slot is not a player.
    team_names:
        The two team names in metadata order. The first is the home team.
    slot_team:
        ``int8`` array of length ``n_slots``: 0 for home, 1 for away.
    player_xy:
        ``(n_frames, n_slots, 2)`` float32 positions in metres; NaN where unobserved.
    player_speed:
        ``(n_frames, n_slots)`` float32 speeds in m/s; NaN where unobserved.
    ball_xy:
        ``(n_frames, 2)`` float32 position in metres; NaN where unobserved.
    ball_speed:
        ``(n_frames,)`` float32 speed in m/s; NaN where unobserved.
    set_pieces:
        List of ``(start_frame, end_frame, kind)`` from Smart Tagging, half-open on the right.
    """

    n_frames: int
    n_slots: int
    team_names: Tuple[str, str]
    slot_team: np.ndarray
    player_xy: np.ndarray
    player_speed: np.ndarray
    ball_xy: np.ndarray
    ball_speed: np.ndarray
    set_pieces: List[Tuple[int, int, str]] = field(default_factory=list)

    @property
    def home_slots(self) -> np.ndarray:
        return np.flatnonzero(self.slot_team == 0)

    @property
    def away_slots(self) -> np.ndarray:
        return np.flatnonzero(self.slot_team == 1)


# --------------------------------------------------------------------------------------------------
# Path resolution
# --------------------------------------------------------------------------------------------------


def data_dir(config: Config) -> str:
    """Where the licensed match data lives."""
    if config.data_dir:
        return os.path.abspath(config.data_dir)
    env = os.environ.get("MTAH_DATA_DIR")
    if env:
        return os.path.abspath(env)
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "data")


def asset_paths(config: Config) -> dict:
    """Absolute paths of the assets of the configured source.

    Naming is derived from the source and the game, exactly as the organisers' own ``games.py``
    does, so a rename is one edit here rather than a hunt through the codebase.
    """
    root = data_dir(config)
    source = config.source
    stem = "BAR-ATH_" + source
    folder = os.path.join(root, source)
    paths = {
        "atd_raw": os.path.join(folder, stem + "_atd.txt"),
        "atd_meta": os.path.join(folder, stem + "_atd.xml"),
        "homography": os.path.join(folder, stem + "_homography.csv"),
    }
    if source == "tactical":
        paths["smart_tagging"] = os.path.join(folder, stem + "_smart_tagging.xml")
    return paths


def missing_assets(config: Config) -> List[str]:
    """Paths of required assets that are not on disk."""
    return [p for p in asset_paths(config).values() if not os.path.isfile(p)]


# --------------------------------------------------------------------------------------------------
# Metadata: teams and track slots
# --------------------------------------------------------------------------------------------------


def parse_meta(meta_path: str) -> Tuple[Tuple[str, str], np.ndarray]:
    """Read team names and the track-slot-to-team mapping from the ATD metadata.

    The metadata lists ``<Team>`` elements with an id and a name, and separately lists
    ``<Player>`` elements with a ``teamId``. The players are *not* nested inside the teams, so a
    parser that looks for ``Team/Player`` finds nothing and silently produces an empty mapping.
    We read both lists and join them on the id.

    Returns the two team names in document order (the first is home) and an ``int8`` array mapping
    each track slot to 0 (home) or 1 (away).
    """
    root = ET.parse(meta_path).getroot()

    team_ids: List[str] = []
    team_names: List[str] = []
    for team in root.iter("Team"):
        team_ids.append(team.get("id"))
        team_names.append((team.findtext("Name") or "").strip())
    if len(team_ids) != 2:
        raise ValueError(
            "{}: expected 2 teams in the metadata, found {}".format(meta_path, len(team_ids))
        )

    id_to_index = {team_id: index for index, team_id in enumerate(team_ids)}
    slot_team: List[int] = []
    for player in root.iter("Player"):
        team_id = player.get("teamId")
        if team_id not in id_to_index:
            raise ValueError(
                "{}: player {} references unknown team {}".format(meta_path, player.get("id"), team_id)
            )
        slot_team.append(id_to_index[team_id])
    if not slot_team:
        raise ValueError("{}: no track slots found in the metadata".format(meta_path))

    return (team_names[0], team_names[1]), np.asarray(slot_team, dtype=np.int8)


# --------------------------------------------------------------------------------------------------
# Smart Tagging: set-piece windows
# --------------------------------------------------------------------------------------------------


def parse_smart_tagging(path: str, fps: float = 25.0) -> List[Tuple[int, int, str]]:
    """Smart Tagging instances as ``(start_frame, end_frame, kind)`` triples.

    Times in the file are seconds from the first frame of the recording, so a frame is
    ``round(seconds * fps)``. Instances are grouped by code in the file, *not* sorted by time, and
    a set piece is tagged as a window around the event rather than the event itself: kick-offs get
    five seconds, other set pieces thirty-five. Callers must treat these as priors, not instants.
    """
    if not os.path.isfile(path):
        return []
    windows: List[Tuple[int, int, str]] = []
    for instance in ET.parse(path).getroot().iter("instance"):
        start = float(instance.findtext("start"))
        end = float(instance.findtext("end"))
        kind = ""
        for label in instance.findall("label"):
            if label.findtext("group") == "Type":
                kind = (label.findtext("text") or "").strip()
        windows.append((int(round(start * fps)), int(round(end * fps)), kind))
    windows.sort()
    return windows


# --------------------------------------------------------------------------------------------------
# Raw tracking
# --------------------------------------------------------------------------------------------------


def read_atd(raw_path: str, n_slots: int, config: Config) -> dict:
    """Stream the raw tracking file into dense arrays.

    Each line is ``frame_id : player ; player ; ... : ball`` with every group being
    ``x,y,speed`` in normalised pitch coordinates and ``NaN`` for a missing observation.

    The ATD frame ids run 1..N, so ``video_frame = frame_id - 1``: the tracking is already on the
    video timeline and there is no offset to discover. The reader asserts that, because a silent
    off-by-one would shift every possession by one frame and cost a fraction of a point that
    nothing would reveal.
    """
    length_m = config.pitch_length_m
    width_m = config.pitch_width_m

    player_xy = np.full((0, n_slots, 2), np.nan, dtype=np.float32)
    player_speed = np.full((0, n_slots), np.nan, dtype=np.float32)
    ball_xy = np.full((0, 2), np.nan, dtype=np.float32)
    ball_speed = np.full((0,), np.nan, dtype=np.float32)

    # We do not know the length up front, so grow geometrically.
    capacity = 1 << 18
    player_xy = np.full((capacity, n_slots, 2), np.nan, dtype=np.float32)
    player_speed = np.full((capacity, n_slots), np.nan, dtype=np.float32)
    ball_xy = np.full((capacity, 2), np.nan, dtype=np.float32)
    ball_speed = np.full((capacity,), np.nan, dtype=np.float32)

    nan = float("nan")
    count = 0
    expected_id = 1

    with open(raw_path, "r", buffering=1 << 20) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            parts = line.split(":")
            if len(parts) != 3:
                raise ValueError(
                    "{}: line {} has {} fields, expected 3".format(raw_path, count + 1, len(parts))
                )
            frame_id = int(parts[0])
            if frame_id != expected_id:
                raise ValueError(
                    "{}: frame ids are not contiguous: expected {}, found {}".format(
                        raw_path, expected_id, frame_id
                    )
                )
            expected_id += 1

            if count == capacity:
                # Grow with NaN padding. np.resize would repeat the contents, which would
                # silently duplicate frames if the file were ever longer than the initial
                # capacity.
                capacity *= 2
                player_xy = np.concatenate(
                    [player_xy, np.full((capacity - count, n_slots, 2), np.nan, dtype=np.float32)]
                )
                player_speed = np.concatenate(
                    [player_speed, np.full((capacity - count, n_slots), np.nan, dtype=np.float32)]
                )
                ball_xy = np.concatenate(
                    [ball_xy, np.full((capacity - count, 2), np.nan, dtype=np.float32)]
                )
                ball_speed = np.concatenate(
                    [ball_speed, np.full((capacity - count,), np.nan, dtype=np.float32)]
                )

            groups = parts[1].split(";")
            if len(groups) != n_slots:
                raise ValueError(
                    "{}: frame {} has {} slots, expected {}".format(
                        raw_path, frame_id, len(groups), n_slots
                    )
                )
            for index, group in enumerate(groups):
                if group[0] == "N":  # 'NaN'
                    continue
                comma = group.find(",")
                second = group.find(",", comma + 1)
                x = float(group[:comma])
                # Some exports carry "x,y" without a speed field; others carry "x,y,speed".
                y = float(group[comma + 1:second] if second > 0 else group[comma + 1:])
                player_xy[count, index, 0] = x * length_m
                player_xy[count, index, 1] = y * width_m
                if second > 0:
                    tail = group[second + 1:]
                    if tail and tail[0] != "N":
                        player_speed[count, index] = float(tail)

            ball = parts[2]
            if ball[0] != "N":
                comma = ball.find(",")
                second = ball.find(",", comma + 1)
                ball_xy[count, 0] = float(ball[:comma]) * length_m
                ball_xy[count, 1] = float(ball[comma + 1:second]) * width_m
                if second >= 0:
                    tail = ball[second + 1:]
                    if tail and tail[0] != "N":
                        ball_speed[count] = float(tail)
            count += 1

    player_xy = player_xy[:count]
    player_speed = player_speed[:count]
    ball_xy = ball_xy[:count]
    ball_speed = ball_speed[:count]
    return {
        "player_xy": player_xy,
        "player_speed": player_speed,
        "ball_xy": ball_xy,
        "ball_speed": ball_speed,
    }


# --------------------------------------------------------------------------------------------------
# The module's interface
# --------------------------------------------------------------------------------------------------


def load_match(config: Config) -> Match:
    """Load a recording completely: metadata, tracking and set pieces.

    Raises ``FileNotFoundError`` naming every missing asset, and ``ValueError`` on any structural
    surprise in the files. It never returns a half-loaded match.
    """
    paths = asset_paths(config)
    missing = [p for p in paths.values() if not os.path.isfile(p)]
    if missing:
        raise FileNotFoundError(
            "match data not found:\n  {}\n\nThe data is gated - see DATA.md. Unpack the bundle "
            "into\n  {}\nor point MTAH_DATA_DIR at wherever you put it.".format(
                "\n  ".join(missing), data_dir(config)
            )
        )

    team_names, slot_team = parse_meta(paths["atd_meta"])
    arrays = read_atd(paths["atd_raw"], int(slot_team.shape[0]), config)

    set_pieces: List[Tuple[int, int, str]] = []
    if "smart_tagging" in paths:
        set_pieces = parse_smart_tagging(paths["smart_tagging"])

    return Match(
        n_frames=int(arrays["player_xy"].shape[0]),
        n_slots=int(slot_team.shape[0]),
        team_names=team_names,
        slot_team=slot_team,
        player_xy=arrays["player_xy"],
        player_speed=arrays["player_speed"],
        ball_xy=arrays["ball_xy"],
        ball_speed=arrays["ball_speed"],
        set_pieces=set_pieces,
    )
