# PLUMB

*To plumb something is to find out where it actually stands.*

**Phase 1 of More Than A Hack 2027** — frame-level ball possession for FC Barcelona vs Athletic
Club, from Metrica's automatic tracking data. The Phase 2 project checks every tracking-derived
claim the same way: it supports one, or refuses it with the reason and what would have to be
collected.

```
python -m mtah.run --out artifacts/submission.csv --report artifacts/run_report.json
```

One command, about three seconds, CPU only, numpy only. The output is the competition's
submission file: `frame,label`, exactly 199,319 rows.

The project this grows into — the thesis, the name and what it has to earn — is in
[`docs/PROJECT.md`](docs/PROJECT.md). How it is shown to the judges is in
[`docs/DEMO.md`](docs/DEMO.md).

**Team: Chappal.** The submission file is `artifacts/Chappal.csv`.

| | |
|---|---|
| **Metric** | `spellF1` — possessions matched one-to-one by temporal IoU, averaged over IoU 0.3–0.7 |
| **Published floor** | `spellF1` 0.2433 (`baseline_smooth50`, scored on the full match) |
| **This system, public 5-minute window** | `spellF1` **0.5000**, `macroF1` 0.6878 — above all four shipped baselines on that window |
| **Possessions** | 306 over the match, 15 in the public window against the organisers' 17 |
| **Runtime** | 2.9 s for the whole match, single core |

The public five minutes are a **correctness check**, never a tuning set — the organisers say
explicitly that the variant that wins on them loses on the full match, and they are right: it
does. Every threshold is tuned on **external** data (Metrica's public sample match, with its own
event annotations), as their clarification email requires. See
[`docs/TECHNICAL.md`](docs/TECHNICAL.md) §5 for the derivation, and
[`scripts/external_tuning.py`](scripts/external_tuning.py) for the harness.

---

## What it does

The task is one question — *who has the ball, right now* — asked 25 times a second for two hours
and thirteen minutes. The hard part is not the geometry; it is that **the ball is missing on
40.69 % of the graded frames**, and that a possession is an *interval*, not a frame.

Three ideas do the work:

1. **Control, not proximity.** A team has the ball when the ball is inside its control radius and
   outside the other team's, and the change has to persist. A touch, a deflection and an aerial
   duel all fail that test, which is exactly the organisers' definition of a change of possession.
2. **Decide in episodes, not frames.** Deciding per frame shattered one 41-second possession into
   seven pieces. Ownership is decided on maximal runs of control and short episodes are absorbed
   into their neighbours before they can become possessions.
3. **Dead ball is a play state, not a missing ball.** In the frames the organisers call dead, the
   ball is *visible* two thirds of the time. What separates them is that the players are not
   running. The test "the ball is untracked and almost nobody is running" is 96 % precise — and it
   is deliberately conservative, because a false dead-ball period splits a real possession in two,
   while a missed one only makes a possession slightly too long.

## The interface

The project is judged on a question going in and something honest coming out — a supported
answer carrying its evidence, or a refusal naming what is missing and what would close the gap.

```
$ plumb ask "who had more possession in the second half?"

  SUPPORTED  Possession share (second-half)
  ──────────────────────────────────────────────────────────────
    Barcelona held the ball for 56.6 % of the live frames.

    Barcelona      56.6 %
    Athletic Club  43.4 %
    live frames    54,226 of 79,390

    coverage       68.3 % of the window's graded frames are live; the ball is observed on 86.7 % of them
    confidence     56.6 % to 69.9 % — the interval is what the unobserved frames allow
    evidence       frames 110,808-190,197

  computed by deterministic code from the raw tracking; no model wrote this claim
```

```
$ plumb ask "which player touched the ball most"

  REFUSED  per-player questions
  ──────────────────────────────────────────────────────────────
    the tracking has no player identities: 46 anonymous track slots for 22 players on the
    pitch, and the organisers warn that slots swap identity as the tracker loses and
    re-acquires people. A slot is not a person.

    missing  an identity-resolved tracking export, or per-player event annotations for this match.
    remedy   identity resolution from a corrected export (the organisers' corrected tracking), or the
             event annotations that arrive with the Innovation Challenge dataset.
    proxy    team-level facts: possession share, possession count and length, dead-ball time, where
             the ball was, and the coverage of the feed itself.
```

The commands are `ask`, `why`, `close-gap`, `coverage` and `ledger`. Everything is local and
deterministic: the router is a rule set, the renderer is a formatter over a structured answer, and
a refusal is exact. No model writes a claim.

### Phase 2: the claim is scoped, and the scope changes the answer

A claim is covered by **its own frames**, not by the match's — the window, the part of the pitch,
or the tactical phase. And the zones are placed by the *last observed* ball position, so the frames
in which the ball was lost are still inside the zone they were lost in. Without that, a zone would
only contain the frames the tracker saw, and its coverage would be 100 % by construction.

| scope | coverage |
|---|---:|
| the whole match | 59.3 % |
| the attacking third | **52.1 %** |
| the `BUILD UP` phases | **92.7 %** |

Neither the final third nor the build-up phases is visible to a global coverage score, and both
change what a club should do.

### The validation: the organisers' own annotation

The Smart Tagging in the bundle is not only set pieces — it is **638 instances over fourteen
codes**, the organisers' own vocabulary for the tactical aspects, and for **140** windows it pairs
an attacking code with a defending code over the same interval and opposite teams. That states who
had the ball, so our labels can be checked against it **without any possession ground truth**.

| check | result |
|---|---:|
| agreement over the 140 mirror pairs | **77.6 %** of 65,724 frames |
| `PROGRESSION` phases | 85.7 % |
| `BUILD UP` phases | 83.2 % |
| the organisers' own `Max Players in the box`, reproduced exactly | **74 of 91** |

Reading that last annotation took a measurement rather than a guess: "Max Players in the box" is
the *defending* team's count, its own players in its own penalty area. Counting the tagged team's
players in the box it *attacks* matches the organisers' number 16 times out of 91; counting the
box it *defends* matches it 74.

### The refusal comes with a collection plan

```
$ plumb close-gap "what happened while the ball was missing"

  PLAN  what would close this gap
  ──────────────────────────────────────────────────────────────

    collect   the ball positions for the frames the tracker did not produce
    how much  64,643 frames (40.7% of the graded ones), in blackouts of up to 221.5 seconds
    unlocks   possession inside the blackouts; every other fact in this build already
              stops at the edge of them
    by when   the organisers' corrected tracking export, which repairs the same gaps
```

A refusal without a remedy is a dead end. This is the piece of work the club takes away.

## Layout

```
src/mtah/
  config.py      every threshold, in metres and seconds
  match.py       load a match: metadata, tracking, set pieces, phases  (deep module)
  teams.py       per-frame team membership (experiment; off by default)
  evidence.py    per-frame evidence: distances, activity, phases, absence classes
  decide.py      ownership, spells, abstentions                (deep module)
  emit.py        write the submission and check it against the official rules
  report.py      what the submission says about itself
  run.py         the command line
src/plumb/
  analysis.py    the possession engine, kept in memory and cached
  coverage.py    the reliability engine: per-frame support, margin, sensitivity
  tactics.py     the six tactical aspects, each with the frames it rests on
  phases.py      the organisers' own annotation, read as a first-class input
  facts.py       the fact library: scope, coverage, confidence, evidence
  router.py      rules, not a model: the question goes to a fact or to a refusal
  plan.py        the collection plan behind every refusal
  cli.py         the command surface
docs/
  PROBLEM.md        the questions the competition asks, and our answers
  PROJECT.md        the name, the thesis, and what Phase 2 has to earn
  ARCHITECTURE.md   the modules and why they are shaped this way
  TECHNICAL.md      the technical document that goes with the submission
  DEMO.md           how it is shown to the judges
  PLAN.md           the plan, from now to the final pitch
  adr/              decisions that were hard to reverse
scripts/          diagnostics: what the public labels mean, and what we get wrong
tests/            158 hermetic tests
```

## Getting the data

The match data is licensed and is **not** in this repository. Enrol, accept the terms, download
the bundle, and unpack it into `data/` (or point `MTAH_DATA_DIR` at it):

```
data/
├─ tactical/   BAR-ATH_tactical.mp4, _atd.xml, _atd.txt, _homography.csv, _smart_tagging.xml
└─ broadcast/  BAR-ATH_broadcast.mp4, _atd.xml, _atd.txt, _homography.csv
```

Verify your copy against the manifest:

```bash
cd data && shasum -a 256 -c ../MANIFEST.sha256
```

## Working on it

```bash
make install     # pip install -e .
make reproduce   # regenerate artifacts/submission.csv
make validate    # check it against the official rules
make test        # 158 tests, under a second
make report      # the run report: possessions, durations, coverage, phases
```

Every number in the technical document comes from `artifacts/run_report.json` or from one of the
scripts in `scripts/`, so it can be regenerated rather than believed.

## The rules we are working under

- The labels must come out of an algorithm. There is no hand-labelling of the provided match
  anywhere in this repository, for training or for validation.
- The competition's data is not uploaded to any hosted service, and it is not committed here.
- The public five minutes are used to check that the pipeline is aligned and to understand the
  organisers' label semantics — never to choose between versions of the system.
- Every threshold is tuned on **external** data, as the organisers' clarification email requires:
  Metrica's public sample match, with its own event annotations, plus a label-free stability
  criterion computed from the tracking. See [`docs/adr/0008-parameters-are-tuned-on-external-data.md`](docs/adr/0008-parameters-are-tuned-on-external-data.md).
