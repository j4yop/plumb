"""The command surface.

    plumb ask "where did we lose the ball most in the second half?"
    plumb coverage --zone attacking-third
    plumb coverage --phase "BUILD UP"
    plumb why "..."
    plumb close-gap "..."
    plumb ledger
    plumb run

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
from .plan import Plan, plan_for
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
    """A supported answer: the claim, the grounds, the provenance.

    A claim the match cannot carry at all is not "supported at zero" — it is unavailable, and
    the header has to say so or the renderer is lying on the fact's behalf.
    """
    unavailable = getattr(fact, "status", "supported") != "supported"
    lines = [
        "  {}  {}".format(
            style.amber("UNAVAILABLE") if unavailable else style.green("SUPPORTED"),
            style.bold(fact.title)),
        "  " + _rule(style),
        "    " + fact.answer,
        "",
    ]
    width = max((len(label) for label, _ in fact.detail), default=0)
    for label, value in fact.detail:
        lines.append("    {}  {}".format(label.ljust(width), value))
    lines.append("")
    if fact.scope:
        lines.append("    {}  {}".format("scope".ljust(width), fact.scope))
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


def render_plan(plan: Plan, style: Style) -> str:
    """A collection plan: the item, the size of the gap, what it unlocks, and by when."""
    lines = [
        "  {}  {}".format(style.cyan("PLAN"), style.bold("what would close this gap")),
        "  " + _rule(style),
        "",
        "    {}  {}".format("collect".ljust(8), plan.collect),
        "    {}  {}".format("how much".ljust(8), plan.how_much),
        "    {}  {}".format("unlocks".ljust(8), plan.unlocks),
    ]
    if plan.by_when:
        lines.append("    {}  {}".format("by when".ljust(8), plan.by_when))
    if plan.steps:
        lines.append("")
        for index, step in enumerate(plan.steps, start=1):
            lines.append("    {}. {}".format(index, step))
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


def _one_line(text: str) -> str:
    """The answer as one line, without chopping a decimal in half."""
    return " ".join(text.split())


def render_ledger(analysis: Analysis, style: Style) -> str:
    """The ledger: one row per claim, with its scope, its coverage, and its status."""
    rows: List[Tuple[str, str, str, str]] = []
    for fact_id, function in FACT_LIBRARY.items():
        try:
            fact = function(analysis, "all")
        except Exception as error:  # a broken fact must not hide the rest of the ledger
            rows.append((fact_id, "could not be computed: {}".format(error), "—", style.red("error")))
            continue
        status = (style.green("supported") if getattr(fact, "status", "supported") == "supported"
                  else style.amber(fact.status))
        rows.append((fact_id, _one_line(fact.answer), fact.coverage_short, status))

    lines = [
        "  {}  {}".format(style.bold("LEDGER"), style.dim("every claim this build makes about the match")),
        "  " + _rule(style),
        "    {}  {}  {}  {}".format(
            style.dim("fact".ljust(22)), style.dim("value".ljust(46)),
            style.dim("coverage".ljust(30)), style.dim("status")
        ),
        style.dim("    coverage = the share of the claim's own scope in which the ball is observed"),
        "",
    ]
    for fact_id, value, coverage, status in rows:
        lines.append("    {}  {}  {}  {}".format(
            fact_id.ljust(22), value[:46].ljust(46), coverage[:30].ljust(30), status
        ))
    lines.append("")
    lines.append(style.dim("  a claim that cannot be supported would appear here as 'refused'"))
    return "\n".join(lines)


def coverage_strip(analysis: Analysis, style: Style, buckets: int = 100,
                   frames: Optional[np.ndarray] = None) -> str:
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
    if frames is not None:
        graded = graded & frames
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


def _phase_frames(analysis: Analysis, code: str) -> np.ndarray:
    """The frames of the Smart Tagging instances with a given code."""
    from . import phases as phase_tools

    frames = np.zeros(analysis.n_frames, dtype=bool)
    for phase in phase_tools.by_code(analysis.phases, code):
        lo = max(0, phase.start)
        hi = min(analysis.n_frames - 1, phase.end)
        if hi >= lo:
            frames[lo:hi + 1] = True
    return frames


def render_coverage(analysis: Analysis, window: str, style: Style,
                    zone: Optional[str] = None, code: Optional[str] = None) -> str:
    """The coverage of the feed, over whatever scope was asked for."""
    from .facts import _graded_frames, _window_slice
    from .tactics import tactics_scope

    frames = _graded_frames(analysis, window)
    scope_text = "the whole match"
    if zone and zone != "all":
        frames = frames & tactics_scope(analysis, zone)
        scope_text = "the {}".format(zone.replace("-", " "))
    if code:
        frames = frames & _phase_frames(analysis, code)
        scope_text = "the {} phases".format(code.lower())

    fact = FACT_LIBRARY["ball_visibility"](analysis, window, zone, code)
    fact.scope = scope_text
    extra = [
        "    {}  {}".format("the feed".ljust(10), coverage_strip(analysis, style, frames=frames)),
        "    {}  {}".format(
            "".ljust(10),
            "each column is about {:,} frames; the height is the share of frames in which "
            "the ball is observed".format(max(1, analysis.n_frames // 100)),
        ),
    ]
    return render_fact(fact, style, extra_lines=extra)


def _ask(analysis: Analysis, question: str, style: Style, as_json: bool) -> int:
    route_ = route(question)

    if route_.kind == "fact":
        fact = FACT_LIBRARY[route_.id](analysis, route_.window, route_.zone, route_.phase)
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
        fact = FACT_LIBRARY[route_.id](analysis, route_.window, route_.zone, route_.phase)
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
    plan = plan_for(analysis, route_)

    if as_json:
        payload = {
            "status": "refused" if route_.kind == "refusal" else "supported",
            "question": question,
            **plan.to_dict(),
        }
        if route_.kind == "refusal":
            payload["refusal"] = route_.detail.to_dict()
        print(json.dumps(payload, indent=2))
        return 0

    if route_.kind == "refusal":
        print(render_refusal(route_.detail, style))
        print("")
        print(render_plan(plan, style))
        return 0

    fact = FACT_LIBRARY[route_.id](analysis, route_.window, route_.zone, route_.phase)
    print(render_fact(fact, style))
    print("")
    print(render_plan(plan, style))
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
    ask.add_argument("--json", action="store_true", dest="as_json",
                     default=argparse.SUPPRESS, help="machine-readable output")
    ask.add_argument("--window", default=None, help="first-half | second-half | halftime | all")
    ask.add_argument("--zone", default=None, help="the part of the pitch the claim is about")
    ask.add_argument("--phase", default=None, help="a Smart Tagging code, e.g. 'BUILD UP'")
    why = sub.add_parser("why", help="why the answer holds, or why it cannot")
    why.add_argument("question")
    why.add_argument("--json", action="store_true", dest="as_json",
                     default=argparse.SUPPRESS, help="machine-readable output")
    why.add_argument("--window", default=None, help="first-half | second-half | halftime | all")
    why.add_argument("--zone", default=None, help="the part of the pitch the claim is about")
    why.add_argument("--phase", default=None, help="a Smart Tagging code, e.g. 'BUILD UP'")
    close = sub.add_parser("close-gap", help="what would have to be collected to answer it")
    close.add_argument("question")
    close.add_argument("--json", action="store_true", dest="as_json",
                       default=argparse.SUPPRESS, help="machine-readable output")
    close.add_argument("--window", default=None, help="first-half | second-half | halftime | all")
    close.add_argument("--zone", default=None, help="the part of the pitch the claim is about")
    close.add_argument("--phase", default=None, help="a Smart Tagging code, e.g. 'BUILD UP'")
    coverage = sub.add_parser("coverage", help="how much of the match the tracking can carry")
    coverage.add_argument("--window", default="all", help="first-half | second-half | halftime | all")
    coverage.add_argument("--zone", default=None, help="the part of the pitch the claim is about")
    coverage.add_argument("--phase", default=None, help="a Smart Tagging code, e.g. 'BUILD UP'")
    sub.add_parser("ledger", help="every claim this build makes, with its coverage")
    run = sub.add_parser("run", help="regenerate the submission and the cache")
    run.add_argument("--out", default="artifacts/submission.csv")
    return parser


WINDOW_PHRASE = {
    "first-half": "in the first half",
    "second-half": "in the second half",
    "halftime": "at half time",
    "all": "over the whole match",
}


def _scoped_question(args, question: str) -> str:
    """Fold an explicit window or zone into the question, so the router sees it."""
    additions = []
    if getattr(args, "window", None):
        additions.append(WINDOW_PHRASE.get(args.window, "in the {}".format(args.window)))
    if getattr(args, "zone", None):
        additions.append("in the {}".format(args.zone.replace("-", " ")))
    if getattr(args, "phase", None):
        additions.append("{} phase".format(args.phase.lower()))
    if additions:
        return "{} {}".format(question, " ".join(additions))
    return question


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
        return _ask(analysis, _scoped_question(args, args.question), style, args.as_json)
    if args.command == "why":
        return _why(analysis, _scoped_question(args, args.question), style, args.as_json)
    if args.command == "close-gap":
        return _close_gap(analysis, _scoped_question(args, args.question), style, args.as_json)
    if args.command == "coverage":
        if args.as_json:
            fact = FACT_LIBRARY["ball_visibility"](analysis, args.window, args.zone, args.phase)
            print(json.dumps(fact.to_dict(), indent=2))
        else:
            print(render_coverage(analysis, args.window, style, args.zone, args.phase))
        return 0
    if args.command == "ledger":
        if args.as_json:
            payload = [
                FACT_LIBRARY[f](analysis, "all").to_dict() for f in FACT_LIBRARY
            ]
            print(json.dumps(payload, indent=2))
        else:
            print(render_ledger(analysis, style))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
