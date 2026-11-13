# The plan

*The project: **PLUMB**. See [`PROJECT.md`](PROJECT.md).*

Two plans: the sprint to the Phase 1 deadline, and the project that follows it. All times are IST.

---

## Phase 1 — the sprint to 18 November, 04:29

The submission deadline is **Wednesday 18 November 2026, 04:29 IST** (11:59 PM CET on the 17th).
The submission form arrives by email on **14 November**. We submit by **20:00 IST on Tuesday 17
November** — an eight-hour buffer — because a form is less forgiving than a folder.

| When | What | Done when |
|---|---|---|
| **12 Nov (now)** | Model locked and re-derived under the organisers' clarification email: control radius and dwell from an external tuning set, merge length from a label-free stability criterion. Public-window `spellF1` 0.5000 | `artifacts/submission.csv` validates against the official rules |
| 12–13 Nov | Email the organisers the five questions in `docs/PROBLEM.md` §5; keep working while waiting | answers, or a plan that does not depend on them |
| 13 Nov | Write the technical document (`docs/TECHNICAL.md`), the README, the ADRs | a stranger could reproduce the result from the repository |
| 14 Nov | **Submit the current file as insurance.** One response per team, editable, last response counted | the form has our file attached |
| 14–16 Nov | Improve only where the *mechanism* is wrong, never where the public score is low: dead-ball classification, hand-over latency, boundary placement | every change justified in the technical document |
| 16 Nov | **Byte-for-byte reproduction rehearsal** from a clean clone, with the data verified against `MANIFEST.sha256` | `make reproduce` produces an identical file |
| 17 Nov 20:00 | Final submission with the technical document and the public repository URL | submitted |

**Rules of the sprint.** The public five minutes are a correctness check, not a tuning set; a
change that only improves them is not a change. Every parameter carries a football justification
and the full-match statistics that support it.

**If the answers to the organisers' questions arrive:** the `D`-onset question (does dead ball
begin at the infringement, the whistle, or the corrected tracking's flag?) is the one that could
change the dead-ball rule. Until it is answered, the conservative rule stands, because it is the
one whose error is cheap.

---

## 18–25 November — de-risk, do not build

The Innovation Challenge dataset (10 professional matches with tracking and event data) does not
arrive until 26 November, so there is nothing to build against.

**What is already done, because it did not need the dataset:**

- [x] The **reliability engine** (`src/plumb/coverage.py`): per-frame support from four automatic
      checks, the decision margin, the sensitivity. Claim-scoped, not match-scoped.
- [x] The **fact library extended beyond possession** (`src/plumb/facts.py`, `src/plumb/tactics.py`):
      eighteen claims — restarts, pressing, build-up, progression, chance creation, defending
      shape, transitions, long balls, players in the box — each keyed to the organisers' own
      Smart Tagging codes.
- [x] The **validation source found**: the Smart Tagging's 140 mirror pairs state who had the
      ball over 65,724 frames, and we agree with them on 77.6 %. We reproduce the organisers' own
      count of players in the box exactly 74 times out of 91. ADR 0009.
- [x] The **refusal gate with collection plans** (`src/plumb/plan.py`): the gap measured in frames
      and seconds, not described.
- [x] The **external tuning harness** extended to Metrica's public sample match, with the
      event-derived possession truth — so the ten-match dataset can be tuned on external data
      from the first hour it lands, exactly as the rules require.

**What is left for this window:**

- Pull two or three **public** Metrica tracking matches (the sample data is open) and hand-label
  formations on them — legal, because the ban is only on the provided match.
- Make the engine **read a directory of matches** rather than one, so the ten-match ledger is a
  configuration change rather than a rewrite.
- Read the briefs when they land on the 26th, and point the work at the aspect the organisers name.

---

## 26 November – 14 January — the Innovation Challenge

The project is built on the 10-match dataset, against the open briefs.

The thesis we are taking: **the bottleneck in club analytics is not insight, it is grounds for
it.** Clubs have tracking and event data; what they cannot do is say which of the numbers they
derive from it survive the gaps in the tracking. The system we have already built is the seed of
that: it makes an explicit, auditable decision about who has the ball on every frame, from
evidence, and it knows exactly how much of the match it could not see.

Three components, in build order:

1. **The reliability engine** — a per-frame coverage model of the tracking (ball visibility,
   player-count anomalies, slot churn, tracking error), with an in-silico error-injection study
   to measure which conclusions survive noise. *This is the same idea as the dead-ball
   classifier, generalised.* — **built; the ten-match re-run is the work.**
2. **The verified fact library** — forty deterministic tactical facts (possession, restarts,
   pressing, build-up, defending, transitions, chance creation), each carrying its evidence
   frames, its coverage basis and a confidence band. Facts are aspect-agnostic, so they survive
   whichever aspect the briefs name. — **eighteen built; the rest to come with the dataset.**
3. **The interface** — local intent routing, deterministic rendering, and a **deterministic
   refusal gate**: when the coverage does not support a claim, the system says so and says what
   would be needed. The language model, if any, classifies the question and nothing else. —
   **built; the ten-match ledger is the work.**

**Kill criteria.** If the coverage engine cannot beat naive coverage on a held-out match, the
project changes shape. If a fact library entry cannot be validated against organiser-provided
labels on the new matches, it does not ship.

**The ledger is the artefact that matters:** one row per claim per match, with what it rests on.
Readable by a human, checkable by a script, and the thing a club would actually take away.

---

## 14 January – 2 March — the pitch

Five teams present on site at Talent Arena. The artefact has to be readable by a jury that has not
seen it before, and it has to run live.

- Weeks 1–2: the demo hardened, the offline fallback prepared, the evaluation tables written up.
- Week 3: rehearsal, and the story — *the question a coach asks, the answer, the proof, and the
  refusal*.
- Week 4: the pitch.
