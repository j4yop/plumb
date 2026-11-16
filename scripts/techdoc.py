"""Build the technical document as a PDF that can be uploaded to the form.

Why this exists
---------------
The form asks for "a short technical document". The source of truth is `docs/TECHNICAL.md`, which
is also the document a reviewer reads in the repository — so the PDF is **generated from it**, not
maintained beside it. Two copies of a technical document is the same failure as two copies of a
pipeline: the one you did not update is the one they read.

The PDF is produced by pandoc (markdown → HTML) and a headless Chrome (HTML → PDF), both of which
print tables and code blocks correctly without a LaTeX install.

    make techdoc
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import re
import subprocess
import sys
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "docs", "TECHNICAL.md")
CSS = os.path.join(ROOT, "docs", "technical-print.css")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# The cover is built here rather than through pandoc's title metadata, because the template's own
# title block renders above the body and collided with it.
FRONT_MATTER = """<div class="cover">

<div class="cover-team">Team <strong>Chappal</strong></div>

<h1 class="cover-title">Frame-level ball possession</h1>
<p class="cover-sub">Technical document — More Than A Hack 2027, Phase 1</p>

<div class="cover-meta">

| | |
|---|---|
| **Repository** | https://github.com/j4yop/plumb |
| **Submission** | `Chappal.csv` — {rows:,} rows, labels `H A D X` |
| **File digest** | `{digest}` |
| **Built** | {built} |
| **Public-window score** | `spellF1` {spell}, `macroF1` {macro} |

</div>

<div class="cover-note">

This document describes a deterministic, CPU-only pipeline that decides who has the ball on every
frame of one match, from Metrica's automatic tracking. It has no model and no fitted parameter.
Every number in it is produced by code in the repository, and the derivation of every threshold is
stated beside the value.

It also reports what the feed cannot carry: the ball is missing on **{missing:.1f} %** of the graded
frames, and that hole is measured rather than hidden.

</div>

</div>

<div class="pagebreak"></div>

"""


def digest() -> str:
    path = os.path.join(ROOT, "artifacts", "Chappal.csv")
    if not os.path.isfile(path):
        return "not built"
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:32]


def score() -> tuple:
    """The two figures the README publishes, read from it rather than retyped."""
    path = os.path.join(ROOT, "README.md")
    text = open(path).read() if os.path.isfile(path) else ""
    spell = re.search(r"`spellF1` \*\*(0\.\d+)\*\*", text)
    macro = re.search(r"`macroF1` (0\.\d+)", text)
    return (spell.group(1) if spell else "—"), (macro.group(1) if macro else "—")


def build(out: str) -> int:
    if not os.path.isfile(SOURCE):
        print("no source at {}".format(SOURCE), file=sys.stderr)
        return 1
    if not os.path.isfile(CSS):
        print("no stylesheet at {}".format(CSS), file=sys.stderr)
        return 1

    body = open(SOURCE).read()
    # The markdown's own H1 becomes the cover's subtitle, so drop it from the body.
    body = re.sub(r"^# .*\n", "", body, count=1)

    spell, macro = score()
    missing = 100.0 * 64643 / 158857
    front = FRONT_MATTER.format(
        rows=199319, digest=digest(),
        built=datetime.date.today().strftime("%d %B %Y"),
        spell=spell, macro=macro, missing=missing,
    )

    combined = os.path.join(ROOT, "artifacts", "_techdoc.md")
    os.makedirs(os.path.dirname(combined), exist_ok=True)
    with open(combined, "w") as handle:
        handle.write(front + body)

    html = os.path.join(ROOT, "artifacts", "_techdoc.html")
    subprocess.run(
        ["pandoc", combined, "-o", html, "--standalone", "--css", CSS,
         "--metadata", "lang=en", "--quiet"],
        check=True,
    )
    os.remove(combined)

    if not os.path.isfile(CHROME):
        print("Chrome not found; the HTML is at {}".format(html), file=sys.stderr)
        return 1

    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         "--virtual-time-budget=4000", "--print-to-pdf={}".format(os.path.abspath(out)),
         "file://{}".format(os.path.abspath(html))],
        check=True, capture_output=True,
    )
    size = os.path.getsize(out) if os.path.isfile(out) else 0
    print("wrote {} — {:,} bytes".format(out, size))
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="build the technical document PDF")
    parser.add_argument("--out", default="artifacts/Chappal-technical-document.pdf")
    args = parser.parse_args(argv)
    return build(args.out)


if __name__ == "__main__":
    sys.exit(main())
