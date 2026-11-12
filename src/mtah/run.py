"""Command line entry point: one command, one submission.

    python -m mtah.run --out artifacts/submission.csv

The stages are the ones in docs/WORKFLOW.md. Every stage prints what it did, because a silent
pipeline is a pipeline nobody can debug at 2am the night before the deadline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict

import numpy as np

from .config import ABSENCE_NAMES, Config, LABEL_NAMES
from .decide import assign_owners, build_spells
from .emit import validate_file, write_submission
from .evidence import build_evidence
from .match import load_match
from .report import summarise
from .teams import assign_teams


def _coerce(value: str):
    """Turn a command-line string into the type the configuration expects."""
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mtah.run", description=__doc__)
    parser.add_argument("--data-dir", default=None, help="where the match data lives (default: $MTAH_DATA_DIR or ./data)")
    parser.add_argument("--source", default="tactical", choices=["tactical", "broadcast"])
    parser.add_argument("--out", default="artifacts/submission.csv", help="submission CSV path")
    parser.add_argument("--report", default="artifacts/run_report.json", help="run report path")
    parser.add_argument("--trace", default=None, help="optional per-frame debug CSV")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a configuration value")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    config = Config(source=args.source, data_dir=args.data_dir or "")
    for item in args.set:
        if "=" not in item:
            raise SystemExit("--set expects key=value, got {!r}".format(item))
        key, raw = item.split("=", 1)
        key = key.strip()
        if not hasattr(config, key):
            raise SystemExit("unknown configuration key: {}".format(key))
        value = _coerce(raw)
        object.__setattr__(config, key, value)  # frozen dataclass, one controlled exception

    started = time.time()

    print("[0] loading the match ...")
    match = load_match(config)
    print(
        "    {} frames, {} track slots, teams {} (home) vs {} (away)".format(
            match.n_frames, match.n_slots, match.team_names[0], match.team_names[1]
        )
    )

    print("[1] building evidence ...")
    teams = None
    if config.neighbour_team_voting:
        print("    assigning teams by spatial neighbours ...")
        teams = assign_teams(match.player_xy, match.slot_team, k=config.neighbour_votes)
        changed = int(np.sum(teams != np.broadcast_to(match.slot_team, teams.shape)))
        print("    {} slot-frames changed team from the metadata".format(changed))
    evidence = build_evidence(match, config, teams=teams)
    print(
        "    ball observed on {:.2f}% of frames ({:.2f}% of graded)".format(
            100.0 * evidence.ball_present.mean(),
            100.0 * evidence.ball_present[evidence.graded].mean(),
        )
    )
    for index in sorted(ABSENCE_NAMES):
        count = int(np.sum(evidence.absence_class == index))
        if count:
            print("    {:<12} {:>8}".format(ABSENCE_NAMES[index], count))

    print("[2] assigning possession ...")
    owners, episodes = assign_owners(evidence, config)

    print("[3] building spells ...")
    decision = build_spells(owners, evidence, config, episodes=episodes)
    print("    {} control episodes (mean {:.1f} s)".format(
        len(episodes),
        float(np.mean([(stop - start) for start, stop, _ in episodes])) / 25.0 if episodes else 0.0))

    print("[4] writing {} ...".format(args.out))
    write_submission(args.out, decision.labels)

    problems = validate_file(args.out, match.n_frames)
    if problems:
        for problem in problems:
            print("    FAIL {}".format(problem))
        return 1
    print("    valid: {} rows, frames 0..{}".format(match.n_frames, match.n_frames - 1))

    summary = summarise(decision.labels, evidence, config, spells=decision.spells)
    summary["config"] = config.as_dict()
    summary["runtime_s"] = round(time.time() - started, 1)
    summary["output"] = args.out
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)

    print("[5] report -> {}".format(args.report))
    print(
        "    possessions {} (mean {:.1f} s) | dead spells {} | H share of alive {:.3f}".format(
            summary["possessions"],
            summary["mean_possession_s"],
            summary["dead_spells"],
            summary["home_share_of_alive"],
        )
    )
    print("    label counts (graded): {}".format(summary["label_counts_graded"]))

    if args.trace:
        _write_trace(args.trace, decision.labels, evidence, match)
        print("    trace -> {}".format(args.trace))

    print("done in {}s".format(summary["runtime_s"]))
    return 0


def _write_trace(path: str, labels, evidence, match) -> None:
    """Per-frame debug dump: the label and the evidence behind it."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as handle:
        handle.write(
            "frame,label,phase,graded,ball_present,absence_class,d_home,d_away,"
            "activity,moving,players_home,players_away,set_piece\n"
        )
        for frame in range(match.n_frames):
            handle.write(
                "{},{},{},{},{},{},{:.2f},{:.2f},{:.3f},{},{},{},{}\n".format(
                    frame,
                    LABEL_NAMES[int(labels[frame])],
                    int(evidence.phase[frame]),
                    int(evidence.graded[frame]),
                    int(evidence.ball_present[frame]),
                    int(evidence.absence_class[frame]),
                    evidence.d_home[frame],
                    evidence.d_away[frame],
                    evidence.activity[frame],
                    int(evidence.moving_players[frame]),
                    int(evidence.players_home[frame]),
                    int(evidence.players_away[frame]),
                    int(evidence.set_piece[frame]),
                )
            )


if __name__ == "__main__":
    sys.exit(main())
