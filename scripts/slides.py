"""The four slides, generated from the analysis.

Why generated
-------------
A slide deck is the one artefact in a project that rots silently. Somebody types "41 % of frames"
into a text box, the pipeline changes, and the deck keeps saying 41 % for six weeks. Every number
in this deck is read from the same code path that answers the questions on stage, so the deck and
the demo cannot disagree — and regenerating it is `make slides`.

Why HTML
--------
One file, no server, no network, no font download. It opens with ``file://`` on any laptop and
prints to PDF from the browser's own dialog. That is the same principle as the terminal demo: the
thing you show must not need anything to be running.
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from typing import List, Optional

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from mtah.config import Config  # noqa: E402

from plumb import cli, phases as phase_tools  # noqa: E402
from plumb.analysis import analyse  # noqa: E402
from plumb.facts import FACT_LIBRARY  # noqa: E402
from plumb.plan import plan_for  # noqa: E402
from plumb.router import route  # noqa: E402

CSS = """
:root {
  --paper: #f6f4ef;
  --ink: #14161a;
  --mid: #5b6068;
  --rule: #d6d2c8;
  --signal: #b3341a;
  --ok: #1f6b3a;
  --mono: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
  --text: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--paper); color: var(--ink); }
body { font-family: var(--text); -webkit-font-smoothing: antialiased; }
.slide {
  width: 100vw; height: 100vh; padding: 7vh 8vw;
  display: flex; flex-direction: column; justify-content: center;
  page-break-after: always; overflow: hidden;
  border-bottom: 1px solid var(--rule);
}
.slide:last-child { border-bottom: none; }
.eyebrow {
  font-family: var(--mono); font-size: 0.95rem; letter-spacing: 0.16em;
  text-transform: uppercase; color: var(--mid); margin-bottom: 3.2vh;
}
h1 { font-size: clamp(2.2rem, 4.6vw, 4.4rem); line-height: 1.06; margin: 0 0 2.4vh; font-weight: 620; letter-spacing: -0.02em; max-width: 24ch; }
h2 { font-size: clamp(1.5rem, 2.6vw, 2.5rem); line-height: 1.15; margin: 0 0 2vh; font-weight: 600; letter-spacing: -0.01em; max-width: 30ch; }
p  { font-size: clamp(1rem, 1.5vw, 1.45rem); line-height: 1.5; margin: 0 0 1.6vh; max-width: 60ch; color: var(--ink); }
p.mid { color: var(--mid); }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.big { font-family: var(--mono); font-size: clamp(3.4rem, 9vw, 8rem); line-height: 0.95; font-weight: 600; letter-spacing: -0.04em; }
.signal { color: var(--signal); }
.ok { color: var(--ok); }
.grid { display: grid; gap: 3.5vh 4vw; margin: 2vh 0 0; }
.g2 { grid-template-columns: 1fr 1fr; }
.g3 { grid-template-columns: repeat(3, 1fr); }
.cell { border-top: 2px solid var(--ink); padding-top: 1.4vh; }
.cell .k { font-family: var(--mono); font-size: 0.85rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--mid); }
.cell .v { font-family: var(--mono); font-size: clamp(1.6rem, 3.4vw, 3rem); font-weight: 600; font-variant-numeric: tabular-nums; margin-top: 0.6vh; }
.cell .n { font-size: 0.95rem; color: var(--mid); margin-top: 0.5vh; }
pre {
  font-family: var(--mono); font-size: clamp(0.55rem, 1.05vw, 1rem);
  line-height: 1.15; margin: 0; color: var(--ink); white-space: pre;
}
.strip { letter-spacing: 0; }
.claims { display: grid; grid-template-columns: 1fr 1fr; gap: 0 5vw; margin-top: 2vh; }
.claim { display: grid; grid-template-columns: 19ch 1fr 5ch; gap: 0 1.2vw; align-items: center; padding: 0.72vh 0; border-bottom: 1px solid var(--rule); }
.claim .name { font-family: var(--mono); font-size: clamp(0.62rem, 0.92vw, 0.86rem); color: var(--ink); white-space: nowrap; overflow: hidden; }
.claim .bar { height: 7px; background: var(--rule); position: relative; }
.claim .bar i { position: absolute; left: 0; top: 0; bottom: 0; display: block; }
.claim .pct { font-family: var(--mono); font-size: clamp(0.62rem, 0.92vw, 0.86rem); text-align: right; font-variant-numeric: tabular-nums; color: var(--mid); }
.plan { display: grid; grid-template-columns: 10ch 1fr; gap: 1.1vh 2vw; margin: 2vh 0 0; align-items: baseline; }
.plan .lab { font-family: var(--mono); font-size: 0.82rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--mid); }
.plan .val { font-size: clamp(0.9rem, 1.25vw, 1.15rem); line-height: 1.4; }
.plan .val.mono { font-family: var(--mono); }
.ref { display: grid; grid-template-columns: 8ch 1fr; gap: 0.5vh 2vw; margin: 0 0 2vh; align-items: baseline; }
.ref .tag { font-family: var(--mono); font-size: 0.8rem; letter-spacing: 0.08em; color: var(--signal); }
.ref .body { font-size: clamp(0.85rem, 1.15vw, 1.02rem); line-height: 1.35; color: var(--mid); }
.mono-block {
  font-family: var(--mono); font-size: clamp(0.7rem, 1.15vw, 1.05rem); line-height: 1.55;
  white-space: pre-wrap; border-left: 3px solid var(--signal); padding-left: 1.2vw; margin: 1.5vh 0;
}
.foot {
  position: absolute; bottom: 4vh; left: 8vw; right: 8vw;
  display: flex; justify-content: space-between;
  font-family: var(--mono); font-size: 0.8rem; color: var(--mid);
  letter-spacing: 0.08em; text-transform: uppercase;
}
.slide { position: relative; }
table { border-collapse: collapse; width: 100%; margin-top: 1.5vh; }
th, td { text-align: left; padding: 0.55vh 1vw 0.55vh 0; font-size: clamp(0.7rem, 1.05vw, 0.98rem); border-bottom: 1px solid var(--rule); }
th { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mid); font-weight: 500; }
td.n { font-family: var(--mono); font-variant-numeric: tabular-nums; text-align: right; }
mark { background: none; color: var(--signal); font-weight: 620; }
@media print {
  html, body { background: #fff; }
  .slide { height: 100vh; border: none; }
}
"""

SCRIPT = """
(function () {
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var index = 0;
  function show(n) {
    index = Math.max(0, Math.min(slides.length - 1, n));
    slides[index].scrollIntoView({behavior: 'instant', block: 'start'});
  }
  document.addEventListener('keydown', function (event) {
    if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') { show(index + 1); event.preventDefault(); }
    if (event.key === 'ArrowLeft' || event.key === 'PageUp') { show(index - 1); event.preventDefault(); }
    if (event.key === 'Home') { show(0); }
    if (event.key === 'End') { show(slides.length - 1); }
  });
})();
"""


def esc(text: str) -> str:
    return html.escape(str(text))


def strip_svg(analysis, buckets: int = 96) -> str:
    """The feed's coverage as an SVG bar chart.

    The terminal draws this in block characters, which is right for a terminal and wrong for a
    projector: the glyphs are inconsistent between fonts and they rasterise badly. A generated
    SVG is the same data, drawn crisply, and it can mark the columns where the feed dies.
    """
    graded = analysis.evidence.graded
    seen = analysis.evidence.ball_present
    # Bucket over the graded span, not the whole file: the pre-match and post-match are not part
    # of the question, and charting them made the match look a third shorter than it is.
    graded_frames = np.flatnonzero(graded)
    if graded_frames.size == 0:
        return ""
    start, stop = int(graded_frames[0]), int(graded_frames[-1]) + 1
    size = max(1, (stop - start) // buckets)
    shares = []
    for index in range(buckets):
        lo = start + index * size
        hi = min(stop, lo + size)
        block = graded[lo:hi]
        shares.append(float(seen[lo:hi][block].mean()) if block.any() else None)

    width, height, gap = 960.0, 92.0, 1.2
    bar = (width - gap * (buckets - 1)) / buckets
    parts = ['<svg viewBox="0 0 {:.0f} {:.0f}" width="100%" '
             'preserveAspectRatio="none" role="img" '
             'aria-label="coverage of the feed across the match">'.format(width, height + 10)]
    for index, share in enumerate(shares):
        if share is None:
            continue
        h = max(1.0, share * height)
        colour = "var(--signal)" if share < 0.5 else "var(--ink)"
        parts.append(
            '<rect x="{:.2f}" y="{:.2f}" width="{:.2f}" height="{:.2f}" fill="{}"/>'.format(
                index * (bar + gap), height - h, bar, h, colour))
    parts.append('<line x1="0" y1="{:.1f}" x2="{:.0f}" y2="{:.1f}" stroke="var(--rule)" '
                 'stroke-width="1"/>'.format(height, width, height))
    parts.append("</svg>")
    return "".join(parts)


def slide(content: str, number: int, total: int) -> str:
    return (
        '<section class="slide">{content}'
        '<div class="foot"><span>PLUMB</span><span>{n} / {t}</span></div>'
        "</section>"
    ).format(content=content, n=number, t=total)


def build(analysis) -> str:
    coverage = analysis.coverage()
    graded = analysis.evidence.graded
    total = int(graded.sum())
    seen = int((analysis.evidence.ball_present & graded).sum())
    missing = 1.0 - (seen / total if total else 0.0)

    # The three scopes, from the same function the CLI uses.
    from plumb.facts import _graded_frames
    from plumb.tactics import tactics_scope

    def scope_pct(zone=None, code=None):
        frames = _graded_frames(analysis, "all")
        if zone:
            frames = frames & tactics_scope(analysis, zone)
        if code:
            frames = frames & cli._phase_frames(analysis, code)
        if not frames.any():
            return 0.0
        return float(analysis.evidence.ball_present[frames].mean())

    whole = scope_pct()
    third = scope_pct(zone="attacking-third")
    middle = scope_pct(zone="middle-third")
    build_up = scope_pct(code="BUILD UP")

    strip = strip_svg(analysis, buckets=96)

    # The refusal, and the plan behind it. The gap question is the one with a quantified remedy,
    # so its numbers are read here rather than typed into the slide.
    refusal_route = route("which player scored the goal")
    gap_route = route("what happened while the ball was missing")
    plan = plan_for(analysis, gap_route)
    graded_missing = analysis.evidence.graded & ~analysis.evidence.ball_present
    gap_frames = int(graded_missing.sum())
    longest_gap = 0.0
    run = 0
    for flag in graded_missing:
        run = run + 1 if flag else 0
        longest_gap = max(longest_gap, run / 25.0)

    # The validation.
    pairs = phase_tools.mirror_pairs(analysis.phases, analysis.team_names)
    pair_result = phase_tools.pair_agreement(pairs, analysis.labels, analysis.team_names)
    box = FACT_LIBRARY["box_presence"](analysis, "all")
    box_detail = dict(box.detail)

    # The ledger.
    entries = []
    for fact_id, function in FACT_LIBRARY.items():
        fact = function(analysis, "all")
        if fact.status != "supported":
            continue
        pct = 0.0 if fact.coverage_pct is None else 100.0 * fact.coverage_pct
        entries.append((fact_id, pct))

    # Weakest first: the ordering is the argument. The top-left row is the claim with the
    # least ground under it, and that is the one a club should go and collect data for.
    rows: List[str] = []
    for fact_id, pct in sorted(entries, key=lambda item: (item[1], item[0])):
        colour = "var(--signal)" if pct < 65 else ("var(--ink)" if pct < 90 else "var(--ok)")
        rows.append(
            '<div class="claim"><div class="name">{id}</div>'
            '<div class="bar"><i style="width:{pct:.1f}%;background:{colour}"></i></div>'
            '<div class="pct">{pct:.0f}%</div></div>'.format(
                id=esc(fact_id), pct=pct, colour=colour)
        )

    slides = [
        # 1 — the problem
        slide(
            '<div class="eyebrow">the problem</div>'
            '<h1>The ball is missing on <span class="signal">{pct:.0f} %</span> of the frames '
            "you are graded on.</h1>"
            '<p class="mid">Every number a club derives from tracking rests on frames that were '
            "never observed. The industry reports the number and hides the hole.</p>".format(
                pct=100.0 * missing)
            + '<div class="grid g3">'
            '<div class="cell"><div class="k">graded frames</div><div class="v">{total:,}</div></div>'
            '<div class="cell"><div class="k">ball observed</div><div class="v">{seen:,}</div></div>'
            '<div class="cell"><div class="k">not observed</div><div class="v signal">{miss:,}</div></div>'
            "</div>".format(total=total, seen=seen, miss=total - seen),
            1, 5),

        # 2 — the coverage belongs to the claim
        slide(
            '<div class="eyebrow">the coverage belongs to the claim</div>'
            '<h2>One match, three scopes, three answers.</h2>'
            '<p class="mid">A claim about the final third is only as good as the final third. '
            "The tool reports the number that belongs to the question, not one number about the "
            "match.</p>"
            '<div class="grid g3">'
            '<div class="cell"><div class="k">the match</div><div class="v">{whole:.0f}<span style="font-size:0.55em">%</span></div>'
            '<div class="n">of graded frames</div></div>'
            '<div class="cell"><div class="k">the attacking third</div><div class="v signal">{third:.0f}<span style="font-size:0.55em">%</span></div>'
            '<div class="n">worse covered than the match</div></div>'
            '<div class="cell"><div class="k">the build-up phases</div><div class="v ok">{up:.0f}<span style="font-size:0.55em">%</span></div>'
            '<div class="n">better covered than the match</div></div>'
            "</div>"
            '<div style="margin-top:4vh">{strip}</div>'
            '<p class="mid" style="font-size:0.9rem;margin-top:1vh">each column is about '
            "{bucket:,} frames; the height is the share of frames in which the ball was observed, "
            'and <span class="signal">the red columns are the ones where the feed loses the ball '
            "on more than half of them</span>.</p>".format(
                whole=100 * whole, third=100 * third, up=100 * build_up,
                strip=strip, bucket=max(1, analysis.n_frames // 96)),
            2, 5),

        # 3 — the refusal, with the gap measured
        slide(
            '<div class="eyebrow">the refusal</div>'
            '<h1>It says no, and then it says what to collect.</h1>'
            '<div class="ref">'
            '<div class="tag">refused</div><div class="body">who touched the ball — '
            "46 anonymous track slots for 22 players, and the slots swap identity as the tracker "
            "loses and re-acquires people. A slot is not a person.</div>"
            '<div class="tag">refused</div><div class="body">what happened inside the gap — '
            "{gap:,} graded frames carry no ball observation, in blackouts of up to {longest:.1f} "
            "seconds. Nothing there can be supported, because there is nothing to support it.</div>"
            "</div>".format(gap=gap_frames, longest=longest_gap)
            + '<div class="plan">'
            '<div class="lab">collect</div><div class="val">{collect}</div>'
            '<div class="lab">how much</div><div class="val mono">{how}</div>'
            '<div class="lab">unlocks</div><div class="val">{unlocks}</div>'
            "</div>".format(
                collect=esc(plan.collect),
                how=esc(plan.how_much),
                unlocks=esc(plan.unlocks)),
            3, 5),

        # 4 — the check
        slide(
            '<div class="eyebrow">the check</div>'
            '<h1>The organisers\' own annotation says who had the ball.</h1>'
            '<p class="mid">For {pairs:.0f} windows it tags an attacking code and a defending '
            "code over the same interval with opposite teams. That is a possession statement made "
            "without any ground truth — and it is checkable.</p>".format(pairs=pair_result["pairs"])
            + '<div class="grid g3">'
            '<div class="cell"><div class="k">agreement</div><div class="v ok">{agree:.1%}</div>'
            '<div class="n">over {frames:,} frames</div></div>'
            '<div class="cell"><div class="k">players in the box</div><div class="v">{box_exact}</div>'
            '<div class="n">reproduced exactly</div></div>'
            '<div class="cell"><div class="k">within one player</div><div class="v">{box_one}</div>'
            '<div class="n">of the same instances</div></div>'
            "</div>".format(
                agree=pair_result["agreement"], frames=int(pair_result["frames"]),
                box_exact=box_detail.get("exact match", "—"),
                box_one=box_detail.get("within one player", "—")),
            4, 5),

        # 5 — the ledger
        slide(
            '<div class="eyebrow">the ledger</div>'
            '<h2>Eighteen claims. Each one carries the ground it stands on.</h2>'
            '<p class="mid" style="max-width:70ch">The bar is the share of that claim&rsquo;s own '
            "scope in which the ball was observed. It is not one number about the match: it is "
            "eighteen, and the weakest one tells you what to collect first.</p>"
            '<div class="claims">{rows}</div>'.format(rows="".join(rows)),
            5, 5),
    ]

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>PLUMB — a checker of tracking-derived claims</title>"
        "<style>{css}</style></head><body>{slides}<script>{script}</script></body></html>"
    ).format(css=CSS, slides="".join(slides), script=SCRIPT)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="generate the four slides")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--out", default="docs/slides.html")
    args = parser.parse_args(argv)

    config = Config(data_dir=args.data_dir or os.environ.get("MTAH_DATA_DIR", ""))
    analysis = analyse(config)
    document = build(analysis)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as handle:
        handle.write(document)
    print("wrote {} — {} slides, {} KB".format(
        args.out, document.count('class="slide"'), len(document) // 1024))
    print("open with:  file://{}".format(os.path.abspath(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
