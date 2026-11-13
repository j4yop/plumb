"""The command surface.

    plumb ask "where did we lose the ball most in the second half?"
    plumb coverage
    plumb why "..."
    plumb close-gap "..."
    plumb ledger

The output rules exist because this thing is meant to be read by a jury at a distance from a
screen: one question per screen, colour separating the evidence from the uncertainty, and the
provenance last. Nothing scrolls.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Tuple

import numpy as np

from mtah.config import AWAY, DEAD, HOME

from .analysis import Analysis, analyse
from .facts import FACT_LIBRARY, Fact
from .router import Route, answerable_questions, route

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
AMBER = "\033[33m"
CYAN = "\033[36m"
RED = "\033[31m"


class Style:
    """Colour, unless it is turned off."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return "{}{}{}".format(code, text, RESET) if self.enabled else text

    def bold(self, text): return self._wrap(BOLD, text)
    def dim(self, text): return self._wrap(DIM, text)
    def green(self, text): return self._wrap(GREEN, text)
    def amber(self, text): return self._wrap(AMBER, text)
    def cyan(self, text): return self._wrap(CYAN, text)
    def red(self, text): return self._wrap(RED, text)


def _rule(style: Style, character: str = "─", width: int = 62) -> str:
    return style.dim(character * width)


def render_fact(fact: Fact, style: Style, extra_lines: Optional[List[str]] = None) -> str:
    """A supported answer: the claim, the grounds, the provenance."""
    lines = [
        "  {}  {}".format(style.green("SUPPORTED"), style.bold(fact.title)),
        "  " + _rule(style),
        "    " + fact.answer,
        "",
    ]
    width = max((len(label) for label, _ in fact.detail), default=0)
    for label, value in fact.detail:
        lines.append("    {}  {}".format(label.ljust(width), value))
    lines.append("")
    lines.append("    {}  {}".format("coverage".ljust(width), fact.coverage))
    lines.append("    {}  {}".format(style.amber("confidence".ljust(width)), fact.confidence))
    lines.append("    {}  {}".format("evidence".ljust(width), fact.evidence))
    if extra_lines:
        lines.append("")
        lines.extend(extra_lines)
    lines.append("")
    lines.append(style.dim("  computed by deterministic code from the raw tracking; "
                           "no model wrote this claim"))
    return "\n".join(lines)


def render_refusal(refusal, style: Style) -> str:
    """A refusal: why, what is missing, the way forward, and the nearest answerable question."""
    lines = [
        "  {}  {}".format(style.amber("REFUSED"), style.bold(refusal.title)),
        "  " + _rule(style),
        "    " + refusal.why,
        "",
        "    {}  {}".format("missing".ljust(8), refusal.missing),
        "    {}  {}".format("remedy".ljust(8), refusal.remedy),
        "    {}  {}".format("proxy".ljust(8), refusal.proxy),
        "",
        style.dim("  a refusal is not a failure of the tool; it is the tool's job"),
    ]
    return "\n".join(lines)


def render_unknown(route: Route, style: Style) -> str:
    lines = [
        "  {}  {}".format(style.amber("NO ROUTE"), style.bold("nothing in the library matches that")),
        "  " + _rule(style),
        "    the question was not recognised as one this build can answer.",
        "",
        "    {}  {}".format(style.dim("answerable"), "these are the questions this build carries:"),
    ]
    for fact_id, example in answerable_questions():
        lines.append("      {}  {}".format(style.cyan(fact_id.ljust(20)), example))
    lines.append("")
    lines.append(style.dim("  ask for something the data cannot support and it will refuse you too"))
    return "\n".join(lines)


def render_ledger(analysis: Analysis, style: Style) -> str:
    """The ledger: one row per fact, with its coverage and its status."""
    graded = analysis.evidence.graded
    total = int(graded.sum())
    seen = int((analysis.evidence.ball_present & graded).sum())
    feed_coverage = "{:.1f} %".format(100.0 * seen / total) if total else "—"

    rows: List[Tuple[str, str, str, str]] = []
    for fact_id, function in FACT_LIBRARY.items():
        fact = function(analysis, "all")
        rows.append((fact_id, fact.answer.split(".")[0], feed_coverage, "supported"))

    lines = [
        "  {}  {}".format(style.bold("LEDGER"), style.dim("every claim this build makes about the match")),
        "  " + _rule(style),
        "    {}  {}  {}  {}".format(
            style.dim("fact".ljust(20)), style.dim("value".ljust(38)),
            style.dim("feed".ljust(10)), style.dim("status")
        ),
        style.dim("    feed = the share of graded frames in which the ball is observed at all"),
        "",
    ]
    for fact_id, value, coverage, status in rows:
        lines.append("    {}  {}  {}  {}".format(
            fact_id.ljust(20), value[:38].ljust(38), coverage.ljust(10),
            style.green(status)
        ))
    lines.append("")
    lines.append(style.dim("  a claim that cannot be supported would appear here as 'refused'"))
    return "\n".join(lines)


def coverage_strip(analysis: Analysis, style: Style, buckets: int = 100) -> str:
    """The feed's coverage across the match, drawn in the terminal.

    Each column is a slice of the match; the height of the block is the share of that slice's
    graded frames in which the ball was observed. It is the picture of the whole problem - the
    places the tracker lost the ball - and it needs no plotting library, no browser and no
    network, so it prints on whatever machine the jury's laptop happens to be.
    """
    levels = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
    graded = analysis.evidence.graded
    seen = analysis.evidence.ball_present
    n = analysis.n_frames
    size = max(1, n // buckets)
    out = []
    for index in range(buckets):
        start = index * size
        stop = min(n, start + size)
        window_graded = graded[start:stop]
        if not window_graded.any():
            out.append(" ")
            continue
        share = float(seen[start:stop][window_graded].mean())
        out.append(levels[min(len(levels) - 1, int(share * len(levels)))])
    return "".join(out)


def render_coverage(analysis: Analysis, window: str, style: Style) -> str:
    fact = FACT_LIBRARY["ball_visibility"](analysis, window)
    return render_fact(fact, style)


def _ask(analysis: Analysis, question: str, style: Style, as_json: bool) -> int:
    route_ = route(question)

    if route_.kind == "fact":
        fact = FACT_LIBRARY[route_.id](analysis, route_.window)
        if as_json:
            print(json.dumps({"status": "supported", "question": question, **fact.to_dict()}, indent=2))
        else:
            print(render_fact(fact, style))
        return 0

    if route_.kind == "refusal":
        refusal = route_.detail
        if as_json:
            print(json.dumps({"status": "refused", "question": question, **refusal.to_dict()}, indent=2))
        else:
            print(render_refusal(refusal, style))
        return 0

    if as_json:
        print(json.dumps({"status": "no_route", "question": question}, indent=2))
    else:
        print(render_unknown(route_, style))
    return 0


def _why(analysis: Analysis, question: str, style: Style, as_json: bool) -> int:
    """Why the answer holds — or why it cannot."""
    route_ = route(question)
    if route_.kind == "fact":
        fact = FACT_LIBRARY[route_.id](analysis, route_.window)
        if as_json:
            print(json.dumps({"status": "supported", "question": question, **fact.to_dict()}, indent=2))
        else:
            print(render_fact(fact, style))
        return 0
    if route_.kind == "refusal":
        refusal = route_.detail
        if as_json:
            print(json.dumps({"status": "refused", "question": question, **refusal.to_dict()}, indent=2))
        else:
            print(render_refusal(refusal, style))
        return 0
    if as_json:
        print(json.dumps({"status": "no_route", "question": question}, indent=2))
    else:
        print(render_unknown(route_, style))
    return 0


def _close_gap(analysis: Analysis, question: str, style: Style, as_json: bool) -> int:
    """What would have to be collected to answer a question we cannot answer."""
    route_ = route(question)
    if route_.kind == "refusal":
        refusal = route_.detail
        payload = {
            "status": "refused",
            "question": question,
            "missing": refusal.missing,
            "remedy": refusal.remedy,
            "proxy": refusal.proxy,
        }
        if as_json:
            print(json.dumps(payload, indent=2))
        else:
            print(render_refusal(refusal, style))
            print("")
            print(style.bold("  TO CLOSE THIS GAP"))
            print("    {}  {}".format(style.dim("collect"), refusal.missing))
            print("    {}  {}".format(style.dim("then"), "the same question becomes answerable, "
                                                         "with the same evidence packet"))
        return 0

    fact = FACT_LIBRARY["ball_visibility"](analysis, route_.window)
    if as_json:
        print(json.dumps({"status": "supported", "question": question, **fact.to_dict()}, indent=2))
    else:
        print(render_fact(fact, style))
        print("")
        print(style.bold("  TO CLOSE THIS GAP"))
        print("    {}  {}".format(style.dim("collect"), "nothing — this one is already answerable"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plumb",
        description="Check tracking-derived claims against what the feed can actually carry.",
    )
    parser.add_argument("--data-dir", default=None, help="where the match data lives")
    parser.add_argument("--source", default="tactical", choices=["tactical", "broadcast"])
    parser.add_argument("--no-colour", action="store_true", help="plain output")
    parser.add_argument("--no-cache", action="store_true", help="recompute instead of reusing the cache")
    parser.add_argument("--json", action="store_true", dest="as_json", help="machine-readable output")

    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="ask a question about the match")
    ask.add_argument("question")
    ask.add_argument("--window", default=None, help="first-half | second-half | halftime | all")
    sub.add_parser("coverage", help="how much of the match the tracking can carry")
    sub.add_parser("ledger", help="every claim this build makes, with its coverage")
    why = sub.add_parser("why", help="why the answer holds, or why it cannot")
    why.add_argument("question")
    close = sub.add_parser("close-gap", help="what would have to be collected to answer it")
    close.add_argument("question")
    run = sub.add_parser("run", help="regenerate the submission and the cache")
    run.add_argument("--out", default="artifacts/submission.csv")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    style = Style(enabled=not args.no_colour and sys.stdout.isatty())

    from mtah.config import Config

    config = Config(source=args.source, data_dir=args.data_dir or "")

    if args.command == "run":
        from mtah.decide import assign_owners, build_spells
        from mtah.emit import validate_file, write_submission
        from mtah.evidence import build_evidence
        from mtah.match import load_match

        match = load_match(config)
        evidence = build_evidence(match, config)
        owners, episodes = assign_owners(evidence, config)
        decision = build_spells(owners, evidence, config, episodes=episodes)
        write_submission(args.out, decision.labels)
        problems = validate_file(args.out, match.n_frames)
        if problems:
            for problem in problems:
                print(style.red("  FAIL " + problem))
            return 1
        print(style.green("  wrote {} — {} rows, valid".format(args.out, match.n_frames)))
        return 0

    analysis = analyse(config, use_cache=not args.no_cache)

    if args.command == "ask":
        question = args.question
        if getattr(args, "window", None):
            from .router import Route  # noqa: F401
            question = "{} in the {} half".format(question, args.window)
        return _ask(analysis, question, style, args.as_json)
    if args.command == "why":
        return _why(analysis, args.question, style, args.as_json)
    if args.command == "close-gap":
        return _close_gap(analysis, args.question, style, args.as_json)
    if args.command == "coverage":
        fact = FACT_LIBRARY["ball_visibility"](analysis, "all")
        if args.as_json:
            print(json.dumps(fact.to_dict(), indent=2))
        else:
            strip = coverage_strip(analysis, style)
            extra = [
                "    {}  {}".format("the feed".ljust(10), strip),
                "    {}  {}".format(
                    "".ljust(10),
                    "each column is about {:,} frames; the height is the share of frames in "
                    "which the ball is observed".format(max(1, analysis.n_frames // 100)),
                ),
            ]
            print(render_fact(fact, style, extra_lines=extra))
        return 0
    if args.command == "ledger":
        if args.as_json:
            payload = [FACT_LIBRARY[f](analysis, "all").to_dict() for f in FACT_LIBRARY]
            print(json.dumps(payload, indent=2))
        else:
            print(render_ledger(analysis, style))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
