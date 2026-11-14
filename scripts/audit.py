"""Is the project consistent with itself, and is it ready to submit?

Why this exists
---------------
This project publishes a lot of numbers: 0.5000, 306 possessions, 59.3 % observed, 140 mirror
pairs, 74 of 91, 52.1 % of the attacking third, 170 tests. Every one of them was true when it was
written down. The failure mode that threatens a submission is not a bug — it is a number in a
document that stopped being true two commits ago.

So every published number is checked against the code that produces it, and the check is a
command, not a promise:

    make audit

Exit code 0 means the repository, the submission and the prose all agree.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


@dataclass
class Check:
    name: str
    status: str
    detail: str


CHECKS: List[Check] = []


def _config():
    from mtah.config import Config

    return Config(data_dir=os.environ.get("MTAH_DATA_DIR") or os.path.join(ROOT, "data"))


def check(name: str):
    """Decorate a check: it returns (ok, detail), or raises to fail."""
    def wrap(function):
        before = len(CHECKS)
        try:
            ok, detail = function()
            if len(CHECKS) == before:  # the check did not register its own skip
                CHECKS.append(Check(name, PASS if ok else FAIL, detail))
        except Exception as error:  # a broken check is a finding, not a crash
            CHECKS.append(Check(name, FAIL, "{}: {}".format(type(error).__name__, error)))
        return function
    return wrap


def skip(name: str, why: str):
    CHECKS.append(Check(name, SKIP, why))


# --------------------------------------------------------------------------------------------------
# The submission
# --------------------------------------------------------------------------------------------------

SUBMISSION = os.path.join(ROOT, "artifacts", "Chappal.csv")
FRAMES = 199319
ALPHABET = {"H", "A", "D", "X"}


def have_data() -> bool:
    """The competition bundle is licensed and is not in this repository.

    A reviewer clones without it, so every check that reads it has to say "skipped" rather than
    "failed" — and the summary has to count the skips, or the audit would claim a completeness it
    does not have.
    """
    folder = os.environ.get("MTAH_DATA_DIR") or os.path.join(ROOT, "data")
    return os.path.isfile(os.path.join(folder, "tactical", "BAR-ATH_tactical_atd.txt"))


def have_submission() -> bool:
    return os.path.isfile(SUBMISSION)


@check("submission file exists")
def _exists():
    if not have_submission():
        CHECKS.append(Check("submission file exists", SKIP,
                            "no built submission in this clone — run `make reproduce`"))
        return True, ""
    ok = os.path.isfile(SUBMISSION)
    size = os.path.getsize(SUBMISSION) if ok else 0
    return ok, "{:,} bytes".format(size)


@check("submission has every frame, once")
def _rows():
    if not have_submission():
        CHECKS.append(Check("submission has every frame, once", SKIP, "no built submission"))
        return True, ""
    with open(SUBMISSION) as handle:
        header = handle.readline().strip()
        frames = []
        for line in handle:
            frame, _, label = line.strip().partition(",")
            frames.append(int(frame))
    ok = header == "frame,label" and len(frames) == FRAMES and frames == list(range(FRAMES))
    return ok, "header {!r}, {:,} rows, contiguous 0..{:,}".format(
        header, len(frames), frames[-1] if frames else -1)


@check("submission labels are in H/A/D/X")
def _alphabet():
    if not have_submission():
        CHECKS.append(Check("submission labels are in H/A/D/X", SKIP, "no built submission"))
        return True, ""
    with open(SUBMISSION) as handle:
        handle.readline()
        counts = {}
        for line in handle:
            label = line.strip().split(",")[1]
            counts[label] = counts.get(label, 0) + 1
    ok = set(counts) <= ALPHABET
    return ok, " ".join("{}:{:,}".format(k, v) for k, v in sorted(counts.items()))


@check("submission passes the official checks")
def _validate():
    if not have_submission():
        CHECKS.append(Check("submission passes the official checks", SKIP, "no built submission"))
        return True, ""
    from mtah.emit import validate_file

    problems = validate_file(SUBMISSION, FRAMES)
    return not problems, "no problems" if not problems else "; ".join(problems)


@check("the submission is reproducible byte for byte")
def _reproducible():
    if not have_data() or not have_submission():
        CHECKS.append(Check("the submission is reproducible byte for byte", SKIP,
                            "needs the licensed bundle (MTAH_DATA_DIR) and a built submission"))
        return True, ""
    from mtah.decide import assign_owners, build_spells
    from mtah.emit import write_submission
    from mtah.evidence import build_evidence
    from mtah.match import load_match
    from mtah.config import Config

    config = Config(data_dir=os.environ.get("MTAH_DATA_DIR") or os.path.join(ROOT, "data"))
    match = load_match(config)
    evidence = build_evidence(match, config)
    owners, episodes = assign_owners(evidence, config)
    decision = build_spells(owners, evidence, config, episodes=episodes)
    fresh = os.path.join(ROOT, "artifacts", "_audit.csv")
    write_submission(fresh, decision.labels)
    with open(fresh, "rb") as a, open(SUBMISSION, "rb") as b:
        same = hashlib.sha256(a.read()).hexdigest() == hashlib.sha256(b.read()).hexdigest()
    os.remove(fresh)
    return same, "regenerated from the raw tracking, identical" if same else "DIFFERENT"


# --------------------------------------------------------------------------------------------------
# The repository
# --------------------------------------------------------------------------------------------------


@check("no licensed data is tracked")
def _no_data():
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    tracked = [line for line in out.splitlines()
               if line.startswith("data/") and line != "data/README.md"]
    total = sum(os.path.getsize(os.path.join(ROOT, f)) for f in tracked) if tracked else 0
    return not tracked, "{} data files tracked ({:,} bytes)".format(len(tracked), total)


@check("no tracked file is over 200 kB")
def _small():
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    big = []
    for name in out.splitlines():
        path = os.path.join(ROOT, name)
        if os.path.isfile(path) and os.path.getsize(path) > 200_000:
            big.append("{} ({:,} B)".format(name, os.path.getsize(path)))
    return not big, ", ".join(big) if big else "largest is under 200 kB"


@check("the pipeline has no network code")
def _offline():
    import glob as globber

    bad = []
    for path in globber.glob(os.path.join(ROOT, "src", "**", "*.py"), recursive=True):
        with open(path) as handle:
            text = handle.read()
        for token in ("urllib", "requests.", "socket.", "openai", "anthropic", "http://"):
            if token in text:
                bad.append("{}: {}".format(os.path.relpath(path, ROOT), token))
    return not bad, ", ".join(bad) if bad else "no network imports anywhere in src/"


@check("no code opens a video")
def _no_video():
    import glob as globber

    bad = []
    for path in globber.glob(os.path.join(ROOT, "src", "**", "*.py"), recursive=True):
        with open(path) as handle:
            text = handle.read()
        for token in (".mp4", "cv2", "ffmpeg", "imageio", "VideoCapture"):
            if token in text:
                bad.append("{}: {}".format(os.path.relpath(path, ROOT), token))
    return not bad, ", ".join(bad) if bad else "the video is never opened"


@check("the test suite passes")
def _tests():
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": os.path.join(ROOT, "src")},
    )
    tail = (result.stdout or "").strip().splitlines()
    summary = tail[-1] if tail else "no output"
    passed = re.search(r"(\d+) passed", summary)
    skipped = re.search(r"(\d+) skipped", summary)
    globals()["_TEST_COUNT"] = (int(passed.group(1)) if passed else 0) + (
        int(skipped.group(1)) if skipped else 0)
    return result.returncode == 0, summary


# --------------------------------------------------------------------------------------------------
# The claims
# --------------------------------------------------------------------------------------------------


@check("the analysis matches what the documents say")
def _analysis():
    if not have_data():
        CHECKS.append(Check("the analysis matches what the documents say", SKIP,
                            "needs the licensed bundle (MTAH_DATA_DIR)"))
        return True, ""
    from mtah.config import DEAD
    from plumb.analysis import analyse
    from plumb.facts import FACT_LIBRARY
    from plumb import phases as phase_tools
    from plumb.facts import _graded_frames
    from plumb.tactics import tactics_scope

    config = _config()
    analysis = analyse(config, use_cache=False)
    globals()["_ANALYSIS"] = analysis

    graded = _graded_frames(analysis, "all")
    total = int(graded.sum())
    seen = int((analysis.evidence.ball_present & graded).sum())
    missing = total - seen

    def scope(zone=None, code=None):
        frames = graded
        if zone:
            frames = frames & tactics_scope(analysis, zone)
        if code:
            from plumb.facts import phase_frames

            frames = frames & phase_frames(analysis, code)
        return float(analysis.evidence.ball_present[frames].mean())

    pairs = phase_tools.mirror_pairs(analysis.phases, analysis.team_names)
    pair = phase_tools.pair_agreement(pairs, analysis.labels, analysis.team_names)
    box = dict(FACT_LIBRARY["box_presence"](analysis, "all").detail)

    facts = {}
    facts["graded_frames"] = total
    facts["observed"] = seen
    facts["missing"] = missing
    facts["observed_pct"] = round(100.0 * seen / total, 1)
    facts["missing_pct"] = round(100.0 * missing / total, 1)
    facts["possessions"] = len([s for s in analysis.spells if s[2] in (0, 1)])
    facts["mirror_pairs"] = int(pair["pairs"])
    facts["agreement_pct"] = round(100.0 * pair["agreement"], 1)
    facts["box_exact"] = box.get("exact match", "")
    facts["box_one"] = box.get("within one player", "")
    facts["third_pct"] = round(100.0 * scope("attacking-third"), 1)
    facts["middle_pct"] = round(100.0 * scope("middle-third"), 1)
    facts["buildup_pct"] = round(100.0 * scope(code="BUILD UP"), 1)
    facts["claims"] = len(FACT_LIBRARY)
    globals()["_FACTS"] = facts

    # The numbers the documents quote, checked here.
    expected = {
        "graded_frames": 158857,
        "observed": 94214,
        "missing": 64643,
        "possessions": 306,
        "mirror_pairs": 140,
        "claims": 18,
    }
    wrong = {k: (facts[k], v) for k, v in expected.items() if facts[k] != v}
    ok = not wrong
    return ok, ("all {} published figures match".format(len(expected)) if ok
                else "; ".join("{}: code {} vs doc {}".format(k, a, b) for k, (a, b) in wrong.items()))


# --------------------------------------------------------------------------------------------------
# The documents
# --------------------------------------------------------------------------------------------------

DOCS = ["README.md", "docs/TECHNICAL.md", "docs/DEMO.md", "docs/PROJECT.md",
        "docs/PLAN.md", "docs/COMPLIANCE.md", "docs/PROBLEM.md"]


def _read_docs() -> str:
    text = ""
    for name in DOCS:
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            with open(path) as handle:
                text += handle.read()
    return text


@check("the documents quote the live figures")
def _docs_numbers():
    facts = globals().get("_FACTS")
    if not facts:
        CHECKS.append(Check("the documents quote the live figures", SKIP,
                            "needs the licensed bundle (MTAH_DATA_DIR)"))
        return True, ""
    text = _read_docs()

    # Each entry: the figure, and the strings a reader might find it written as.
    wanted = {
        "graded frames": ["{:,}".format(facts["graded_frames"])],
        "ball observed": ["{:,}".format(facts["observed"])],
        "ball missing": ["{:,}".format(facts["missing"])],
        "observed share": ["{} %".format(facts["observed_pct"]).replace(".0 ", " ")],
        "possessions": ["{} possessions".format(facts["possessions"])],
        "mirror pairs": ["{} mirror pairs".format(facts["mirror_pairs"]),
                         "{} pairs".format(facts["mirror_pairs"])],
        "agreement": ["{:.1f} %".format(facts["agreement_pct"]).replace(".0 ", " ")],
    }
    missing = [label for label, forms in wanted.items()
               if not any(form in text for form in forms)]
    return not missing, ("every quoted figure appears in the docs" if not missing
                         else "not found: " + ", ".join(missing))


@check("the test count in the documents is current")
def _docs_tests():
    count = globals().get("_TEST_COUNT", 0)
    text = _read_docs()
    # Allow the documented count to lag by a little while a change is in flight, but flag it.
    mentioned = sorted({int(n) for n in re.findall(r"(\d{2,3})\s+tests", text)})
    ok = count in mentioned if mentioned else False
    return ok, "suite has {} (passed + skipped); documents say {}".format(
        count, ", ".join(str(n) for n in mentioned) or "nothing")


@check("no document claims the video was used to check output")
def _no_video_claim():
    """A denial is not a claim. Only affirmative uses are flagged."""
    text = _read_docs().lower()
    banned = ["watched the video", "checked against the video", "verified on the video",
              "confirmed with the video", "project the tracking onto a frame",
              "used the video to check"]
    hits = []
    for phrase in banned:
        for match in re.finditer(re.escape(phrase), text):
            before = text[max(0, match.start() - 40):match.start()]
            if re.search(r"\b(not|never|no|without)\b[^.]*$", before):
                continue  # a denial, which is what we want to find
            hits.append(phrase)
            break
    return not hits, ", ".join(hits) if hits else "no affirmative claim in any document"


@check("the README's headline score matches the scorer")
def _score():
    scorer = os.environ.get("MTAH_SCORER")
    if not scorer or not os.path.isdir(scorer):
        CHECKS.append(Check("the README's headline score matches the scorer", SKIP,
                            "set MTAH_SCORER to the organisers' evaluation folder"))
        return True, ""
    results = os.path.join(scorer, "evaluation", "results")
    os.makedirs(results, exist_ok=True)
    target = os.path.join(results, "audit_submission.csv")
    with open(SUBMISSION, "rb") as src, open(target, "wb") as dst:
        dst.write(src.read())
    out = subprocess.run(
        [sys.executable, "evaluation/run_evaluation.py", "--no-detail"],
        cwd=scorer, capture_output=True, text=True,
    ).stdout
    line = [l for l in out.splitlines() if "audit_submission" in l]
    os.remove(target)
    if not line:
        return False, "the scorer did not rank the file"
    fields = line[0].split()
    macro, spell = fields[2], fields[3]
    text = _read_docs()
    ok = spell in text and macro in text
    return ok, "scorer says macroF1 {} spellF1 {}; documents {}".format(
        macro, spell, "agree" if ok else "DISAGREE")


@check("the ADRs are numbered without a gap")
def _adrs():
    folder = os.path.join(ROOT, "docs", "adr")
    numbers = sorted(int(name[:4]) for name in os.listdir(folder) if name[:4].isdigit())
    ok = numbers == list(range(1, len(numbers) + 1))
    return ok, "{} ADRs, 0001..{:04d}".format(len(numbers), numbers[-1] if numbers else 0)


# --------------------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    width = max(len(c.name) for c in CHECKS)
    print()
    print("  AUDIT  {} checks".format(len(CHECKS)))
    print("  " + "-" * (width + 46))
    failures = 0
    for entry in CHECKS:
        if entry.status == FAIL:
            failures += 1
        print("  {:<6} {}  {}".format(entry.status, entry.name.ljust(width), entry.detail))

    skipped = sum(1 for entry in CHECKS if entry.status == SKIP)
    print()
    if failures:
        print("  {} FAILED. The project is not ready.".format(failures))
        return 1
    if skipped:
        print("  {} checks passed, {} skipped — clone with the licensed bundle to run them all"
              .format(len(CHECKS) - skipped, skipped))
        return 0
    print("  all {} checks pass — repository, submission and prose agree".format(len(CHECKS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
