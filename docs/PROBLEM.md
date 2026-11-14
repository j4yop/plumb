# The problem, the questions, and our answers

> Sources for every quotation: `metrica-sports/more-than-a-hack-2027` (`CHALLENGE.md`, `DATA.md`, `EVALUATION.md`, `SUBMISSION.md`, `RULES.md`, `FAQ.md`, `OVERVIEW.md`) and the official Drive bundle, which we audited in full.
> Terminology in **bold** is defined in [`GLOSSARY.md`](../GLOSSARY.md).

---

## 1. The competition, in one paragraph

**More Than A Hack 2027** (Metrica Sports, FC Barcelona Innovation Hub, Mobile World Capital Barcelona) runs in three stages. **Phase 1 — Initial Challenge** (20 Oct – 17 Nov 2026) asks one question about one real match and is ranked **automatically**; the top 20 teams advance to the **Innovation Challenge** (26 Nov – 14 Jan 2027), where 10 professional matches with tracking and event data are released with open design briefs; five teams then pitch on site at Talent Arena on 2 March 2027.

Two consequences shape everything:

- **Phase 1 has no project.** It has a number: `spellF1` on a private full-match ground truth. A beautiful idea cannot move it.
- **Phase 2 has no published brief.** The organisers name "the aspects of the game they deem most relevant" on 26 November. Any project must therefore be built on an **aspect-agnostic spine**.

---

## 2. The questions Phase 1 actually asks

### Q1. "For every frame of the match, say who has the ball."

199,319 frames of the tactical video at 25 fps (2 h 12 m 52.8 s). One label per frame:

| label | meaning |
|---|---|
| `H` | Barcelona in possession, ball alive |
| `A` | Athletic Club in possession, ball alive |
| `D` | dead ball — the ball is not in play |
| `X` | no answer — the system declines to guess, or the frame has no ground truth |

**Our answer.** A per-frame **state machine** with three evidence paths, in priority order:

1. **Ball observed** → attribute to the team of the nearest *controlled* player, subject to control-radius and hysteresis rules (Q2).
2. **Ball not observed** → classify the absence (Q3). Dead → `D`. Live but unobserved → carry the previous owner forward, or `X` if no owner is defensible.
3. **Outside the match** → `X` (never scored, costs nothing).

### Q2. "When does possession change hands?"

> *"A change of possession occurs when a player from the opposing team gains **controlled** possession of the ball… a simple touch of the ball without control, a deflection of a pass that does not intercept it, an aerial duel won without subsequent control of the ball"* — *does not* count.

> *"In phases where the ball is contested or loose, possession stays with the last team that had it."*

**Our answer.** Control is proxied by three rules applied to the distance between the ball and each tracked player (metres, on a 105.3 × 68.0 m pitch):

- **Control radius** — a player controls the ball only within `CONTROL_RADIUS_M`. Beyond it, the ball is not "controlled" by anybody.
- **Hysteresis margin** — a team only *loses* possession when the opponent is closer by at least `HANDOVER_MARGIN_M`. This is what rejects a touch or a deflection: the ball has to arrive at a player who is *meaningfully* closer than the current owner.
- **Minimum dwell** — a change must persist for `MIN_HANDOVER_FRAMES` before it counts, so a single frame of tracking noise cannot split a possession.

Two rules handle the loose-ball cases explicitly:

- **Long ball / contested** — ball is fast, and nobody is within the control radius: possession stays with the last team that had it (the team that kicked it), matching "possession stays with the last team that had it".
- **Tracking absence** — if the ball is not observed, we do **not** invent a turnover; we carry the last owner forward until the evidence says otherwise.

### Q3. "What counts as dead ball?"

> *"The referee determines when the ball is in play."*
> *"The ground truth is derived from corrected tracking data… a frame is `D` where the corrected tracking marks the ball dead, and otherwise takes the team the tracking names as owning it."*
> *"Dead-ball ownership is deliberately not asked for."*

**Our answer.** Dead ball is **not** inferred from ball absence. Absence has four distinct causes and they need different labels. We classify each absent-ball frame using evidence that is available in the delivered data:

| cause | evidence | label |
|---|---|---|
| **Stoppage** | ball absent **and** match-level activity has collapsed (few players moving above a walking threshold) | `D` |
| **Occlusion / live play** | ball absent **and** players are moving (pressing, running, contesting) | carry the previous owner |
| **Ball out of play** | last observed ball position was outside the pitch rectangle | `D` |
| **Warm-up / pre-match / post-match** | published **phase boundaries** (the two halves and the graded window) plus low player counts | `D` (graded frames only) |

We additionally use **Smart Tagging set-piece windows** as a prior for restarts, and we force `D` on the **2,934 graded frames** between the second-half graded window and the second-half kickoff, which are a warm-up, not play.

**Why this matters so much:** the ball is missing on **40.69 %** of graded frames, and during halftime the ball is *present* on **94.07 %** of frames while ~12.5 players are warming up. "Ball visible ⇒ alive" is wrong in both directions, and "ball absent ⇒ dead" is wrong too.

### Q4. "How are we scored?"

> Ranked on **`spellF1`** — "how many of the match's real possessions you recovered as whole possessions". `macroF1` is reported and is the first tie-break.

The ranking metric treats a possession as an **interval**, matched one-to-one against the truth by temporal IoU, averaged over thresholds 0.3–0.7. Consequences for how we build:

- **Over-segmentation is punished twice** — a spurious possession costs precision *and* breaks the true one it split.
- **A one-frame offset is free; a one-second offset costs ~35 %** of the score.
- **`X` is not symmetric across metrics.** `macroF1` charges an `X` on a graded frame as a miss. `spellF1` never sees it: the scorer forward-fills each `X` with the last non-`X` label **in the same half**. So on the ranking metric an `X` really means *"repeat my previous answer"*.
  - Abstaining **inside** a possession is free on `spellF1` and protects the spell.
  - Abstaining **across a hand-over** is expensive: the previous label is carried into the new state.
  - **Therefore: never emit `X` adjacent to a hand-over. Guess there.**
- **Differences below ~0.04 (spellF1) are noise** on the full match, so we chase real gaps, not decimals.

### Q5. "What may we use, and what must we deliver?"

Any method, provided it is inspectable and documented, and the labels come from an algorithm. **No hand labels on the provided match** for any purpose (training *or* validation); hand labels on **other** matches are allowed and must be documented. No private ground truth, and no human-produced data about this match from any source. The competition's data must not be uploaded to any third-party cloud LLM. The data must not be redistributed. Our repository must regenerate the submitted file.

**Our answer.** A deterministic, CPU-only, numpy-only pipeline with no model in the inference path at all; no hand labels anywhere in Phase 1; the repository ships code plus a **checksummed download manifest** instead of the licensed data; every number in the technical document is produced by code that ships with it.

---

## 3. The three deliverables

| # | Deliverable | What it is | How we satisfy it |
|---|---|---|---|
| 1 | **Possession file** | `frame,label` CSV, exactly 199,319 rows, frames 0…199,318 in order, labels in `H A D X`, no blank cells | `src/mtah/emit.py` + `src/mtah/emit.py`, checked by the official `validate_submission.py` |
| 2 | **Public repository** | source, pinned dependencies, install/run instructions, the command that regenerates the file | `pyproject.toml` (pinned), `make reproduce`, `MANIFEST.sha256` |
| 3 | **Technical document** | a few pages: approach and why, assets used and dropped, training data, possession rules implemented, limitations, reproduction | `docs/TECHNICAL.md` |

---

## 4. Why the obvious approach fails

The reference baseline — nearest tracked player to the ball, then a majority vote over a window — is the floor to beat (`spellF1` 0.2433 on the full match). On the public 5-minute window it scores `spellF1` 0.0378 un-smoothed: it reports **131 possessions where the truth has 17**, because per-frame decisions flicker. Its `D` class is weak because it equates "ball not tracked" with "ball dead".

Everything in our design exists to fix one of those two failures:

| Failure | Our countermeasure |
|---|---|
| Per-frame flicker → hundreds of tiny possessions | hysteresis + minimum dwell + minimum spell duration + same-team merging; we optimise **intervals**, not frames |
| Ball absence misread as death | four-way absence classification (Q3) using activity, bounds and phase |
| Hand-over triggered by a touch or deflection | control radius + handover margin + minimum dwell |
| Unknown hand-over state | `X` used as a *sparing*, never-adjacent-to-hand-over abstention |
| Wrong horizon (per-frame vs. possession) | every tunable is expressed in seconds or metres, not frames |

---

## 5. Scope, honestly stated

**In scope for Phase 1:** the possession file, the repository, the technical document.

**Deliberately out of scope for Phase 1:** the Phase 2 project (built 26 Nov – 14 Jan on 10 matches with event data), any use of the broadcast recording (it is not frame-aligned to the tactical video and its homography is valid on only 65.81 % of frames), and any model training (there is no permitted training signal for this match).

**Known open questions** — sent to the organisers on 13 November. Their reply was that *"all the
information we can share has already been provided"*, so **none of these will be answered** and each
one is decided here on the merits:

| question | decision |
|---|---|
| 1. Does `D` begin at the infringement, the whistle, or the corrected tracking's dead-ball flag? | **All three rules are implemented and measured** (`Config.dead_onset`). They differ by one possession over a whole match and by nothing on the public window, so the default — the whistle — stands. The corrected tracking's own flag is data we do not have; if that is the intended answer, the honest response is to ask for the export, not to guess. See ADR 0010. |
| 2. When the ball is untracked during live play, is the truth `H`/`A` or `D`? | **`H`/`A`.** The truth comes from the *corrected* tracking, which repairs the occlusion; a gap in the raw feed is not a stoppage. The owner is carried forward until the ball is seen again. |
| 3. Is the submission editable, last response counted? | **Yes** — `SUBMISSION.md` says so. The early baseline is uploaded as insurance on 14 November and the final file replaces it. |
| 4. What is in the Phase-2 package? | Unknown until 26 November. The library is written so that a new match is a configuration, not a rewrite. |
| 5. How are the 20 → 5 selected? | Unknown. The repository, the technical document, the compliance page and the demo are all built to stand on their own. |
