"""The five minutes, as a script.

Why this exists
---------------
The demo is five beats on somebody else's laptop, and a demo that has only ever been run by hand
is a demo that has only ever been run once. This script runs the identical sequence from the
committed code, so it can be:

* **rehearsed** — ``python3 scripts/demo.py --pause`` waits for Enter between beats;
* **recorded** — ``python3 scripts/demo.py --record artifacts/demo.txt`` writes the transcript that
  becomes the fallback;
* **checked** — it asserts the properties the pitch depends on, so a regression is caught by the
  script rather than by the jury.

The beats, and why each one is there:

1. **An answer.** Fast, with its evidence, no preamble.
2. **A refusal.** The question a confident system would answer wrongly.
3. **The scope.** The same coverage question, asked about a part of the pitch — the tool reports
   the number that belongs to the claim, not one number about the match.
4. **The gap, measured.** A collection plan, not a complaint.
5. **The validation and determinism.** The organisers' own annotation, and the same answer twice.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mtah.config import Config  # noqa: E402

from plumb import cli  # noqa: E402
from plumb.analysis import analyse  # noqa: E402


class Transcript:
    """Collects everything printed, so the recording is the run and not a copy of it."""

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.lines: List[str] = []

    def __call__(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def save(self, extra: str = "") -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w") as handle:
            handle.write("\n".join(self.lines))
            if extra:
                handle.write("\n" + extra)


def provenance() -> List[str]:
    """What this transcript was recorded from: the commit, and the data it read.

    A fallback recording is only worth having if a reviewer can tell *exactly* what produced it.
    The commit pins the code; the manifest pins the licensed data; the two together mean a
    disputed line can be replayed rather than argued about.
    """
    lines = ["", "  recorded from"]
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), text=True, stderr=subprocess.DEVNULL
        ).strip()
        lines.append("    commit      {}".format(commit))
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        lines.append("    commit      (not a git checkout)")

    manifest = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "MANIFEST.sha256")
    if os.path.isfile(manifest):
        with open(manifest, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()[:16]
        lines.append("    data        MANIFEST.sha256, sha256 {}".format(digest))
    else:
        lines.append("    data        no MANIFEST.sha256 on this machine")
    return lines


def beat(transcript: Transcript, number: int, title: str, pause: bool) -> None:
    if pause:
        input("\n  -- press Enter for beat {} --".format(number))
    transcript("")
    transcript("=" * 72)
    transcript("  BEAT {}  {}".format(number, title))
    transcript("=" * 72)
    transcript("")


def run(capsys_module, args: List[str]) -> str:
    """Run one CLI command and return what it printed."""
    from io import StringIO
    import contextlib

    buffer = StringIO()
    with contextlib.redirect_stdout(buffer):
        cli.main(args)
    return buffer.getvalue().rstrip("\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="run the five-minute demo")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--pause", action="store_true", help="wait for Enter between beats")
    parser.add_argument("--record", default=None, help="write the transcript here")
    args = parser.parse_args(argv)

    transcript = Transcript(args.record)
    config = Config(data_dir=args.data_dir or os.environ.get("MTAH_DATA_DIR", ""))
    analysis = analyse(config)

    # The provenance line the whole pitch rests on.
    transcript("")
    transcript("  plumb — a local, deterministic checker of tracking-derived claims")
    transcript("  the data never leaves this machine; the reasoning is deterministic;")
    transcript("  every answer ships its sources")
    transcript("")
    transcript("  match: {} v {}, {:,} frames, {} track slots".format(
        analysis.team_names[0], analysis.team_names[1],
        analysis.n_frames, analysis.slot_team.shape[0]))

    # --- 1. an answer ------------------------------------------------------------------------
    beat(transcript, 1, "a question, answered", args.pause)
    transcript(run(None, ["--no-colour", "ask", "how did they build up in the first half"]))

    # --- 2. a refusal ------------------------------------------------------------------------
    beat(transcript, 2, "a question the data cannot carry", args.pause)
    transcript(run(None, ["--no-colour", "ask", "which player scored the goal"]))

    # --- 3. the scope ------------------------------------------------------------------------
    beat(transcript, 3, "the coverage belongs to the claim, not to the match", args.pause)
    for zone in ("attacking-third", "middle-third"):
        out = run(None, ["--no-colour", "coverage", "--zone", zone])
        keep = [line for line in out.splitlines() if "the feed" in line or "ball observed" in line]
        transcript("  {:<20} {}".format(zone.replace("-", " "), keep[0].strip() if keep else ""))
    out = run(None, ["--no-colour", "coverage", "--phase", "BUILD UP"])
    keep = [line for line in out.splitlines() if "ball observed" in line]
    transcript("  {:<20} {}".format("build up phases", keep[0].strip() if keep else ""))
    transcript("")
    transcript("  the same match, three scopes, three different numbers — and the tool")
    transcript("  reports the one that belongs to the claim.")

    # --- 4. the gap, measured ----------------------------------------------------------------
    beat(transcript, 4, "what would close the gap", args.pause)
    transcript(run(None, ["--no-colour", "close-gap", "what happened while the ball was missing"]))

    # --- 5. the validation and determinism ---------------------------------------------------
    beat(transcript, 5, "the check, and the same answer twice", args.pause)
    out = run(None, ["--no-colour", "ask", "do we agree with the smart tagging"])
    transcript(out)

    first = run(None, ["--no-colour", "ask", "who had more possession"])
    second = run(None, ["--no-colour", "ask", "who had more possession"])
    digest = hashlib.sha256(first.encode()).hexdigest()[:16]
    transcript("")
    transcript("  determinism: the same question, asked twice")
    transcript("    first  sha256 {}".format(digest))
    transcript("    second sha256 {}".format(hashlib.sha256(second.encode()).hexdigest()[:16]))
    assert first == second, "the same question produced two different answers"
    transcript("    identical — computed, not remembered")

    # --- the properties the pitch depends on ---------------------------------------------------
    fact = cli.FACT_LIBRARY["annotation_agreement"](analysis, "all")
    pairs_line = [line for line in out.splitlines() if "mirror pairs" in line]
    assert pairs_line, "the annotation check did not report the mirror pairs"
    assert "coverage" in run(None, ["--no-colour", "ask", "who had more possession"])

    transcript("")
    transcript("  end of demo. {} beats, {} lines of evidence.".format(5, len(transcript.lines)))
    for line in provenance():
        transcript(line)

    transcript.save(extra="\n# recorded from the committed code path; no hand editing")
    if args.record:
        print("\n  transcript written to {}".format(args.record))
    return 0


if __name__ == "__main__":
    sys.exit(main())
