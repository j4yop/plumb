# Workflow — how one submission is produced

Ten stages, one command. Every stage is deterministic and independently testable; the pipeline can stop at any stage and still leave a useful artefact on disk.

```
 0  SETUP        resolve the data directory, verify checksums
 1  READ         stream the ATD, one record per video frame
 2  PROVENANCE   map track slots -> teams, from the ATD metadata
 3  FEATURES     per-frame, per-team geometric and motion evidence
 4  PHASE        classify each frame: pre-match / 1st half / halftime / 2nd half / post-match
 5  ABSENCE      classify every ball-absent frame: stoppage / occlusion / out-of-play / warm-up
 6  POSSESSION   attribute the ball to a controlled player, with hysteresis and minimum dwell
 7  SPELLS       build possession spells, merge, smooth, and place abstentions
 8  WRITE        emit the 199,319-row frame,label CSV
 9  VALIDATE     run the official checks, then score against the public 5 minutes
```

The command:

```bash
python -m mtah.run --source tactical --out artifacts/submission.csv
```

---

## Stage 0 — Setup

`MTAH_DATA_DIR` (default `./data`) is resolved, and each expected file is checked for existence and, if a manifest is present, for its SHA-256. Nothing is downloaded by the pipeline: the match data is licensed and is **never** committed. The repository ships `MANIFEST.sha256` so a reviewer can verify their own copy.

**Output:** a resolved `DataPaths` object, or a readable error naming every missing file.

## Stage 1 — Read

The ATD raw file is streamed line by line. Each line is

```
frame_id : player ; player ; … ; player : ball
```

with each group being `x,y,speed` in **normalised pitch coordinates** (0–1), `NaN` for a missing observation. The reader yields, per video frame:

- the ball's position and speed,
- the per-slot player positions and speeds.

Coordinates are converted to **metres** on read using the measured pitch (105.3 × 68.0 m) so every downstream threshold is in a unit a football person can reason about. Out-of-range coordinates are kept but flagged — they are evidence, not noise to be silently clipped.

**Contract:** `video_frame = frame_id - 1`. The ATD is already on the video timeline; there is no offset to discover. A reader that saw a different count than the metadata expects must fail loudly.

## Stage 2 — Provenance

The ATD metadata XML lists teams and, separately, the track slots with the team each belongs to. We read that mapping rather than assuming slot order, so the pipeline does not silently invert the sides if the export order changes. **Team order defines `H` and `A`: the first team in the metadata is home.**

**Failure mode this kills:** swapping `H` and `A` does not look wrong in a dashboard — it looks like a bad game. Getting it from the metadata instead of a constant is the cheapest insurance there is.

## Stage 3 — Features

Per frame, per team, we compute:

| feature | why |
|---|---|
| ball position, speed, on-pitch flag | the primary evidence; a ball outside the pitch rectangle was put out of play |
| distance from the ball to each tracked player | control evidence |
| nearest player per team, and the distance gap | the hand-over decision |
| players present per team, and in total | distinguishes match play from warm-up |
| player speeds: mean, max, count above a walking threshold | **activity** — the evidence that separates a stoppage from an occlusion |
| team centroid, team spread | collective shape; used by the Phase 2 fact library |
| distance from the ball to each team's centroid | which side is nearer the ball |

All thresholds live in one configuration object, in **seconds and metres**, never in frames.

## Stage 4 — Phase

The published phase boundaries (from the organisers' own documentation) give the coarse phase of every frame. The pipeline does not rely on them alone: it corroborates them with the observed player counts and activity, and it **logs any disagreement**. A data-driven phase estimate is kept alongside the published one so that a future match, with different boundaries, can be handled by the same code path.

**Why this stage exists:** during halftime the ball is present on 94 % of frames with ~12.5 players on the pitch. Any pipeline that infers "alive" from "ball visible" will label the warm-up as possession, and the warm-up contains 2,934 graded frames that must all be `D`.

## Stage 5 — Absence classification

Every frame without a ball observation is classified into exactly one of:

| class | condition | consequence |
|---|---|---|
| `OUT_OF_PLAY` | the last observed ball was outside the pitch rectangle | `D` |
| `STOPPAGE` | ball absent **and** activity below the stoppage threshold | `D` |
| `WARMUP` | the frame falls in a non-graded or warm-up phase | `D` where graded, `X` elsewhere |
| `OCCLUSION` | ball absent **and** activity above the threshold | possession is carried forward, not invented |

Smart Tagging set-piece windows are applied as a **prior**: a frame inside a set-piece window with low activity is a restart, not an occlusion.

**This is the stage the reference baseline gets wrong.** "Ball missing ⇒ dead" is wrong for occlusions during live play, and "ball visible ⇒ alive" is wrong for the warm-up.

## Stage 6 — Possession

For frames with a ball observation:

1. Find the nearest tracked player **within the control radius**. If nobody is within it, the ball is contested or in flight → possession stays with the last team that had it.
2. Compare the two teams' nearest-player distances. The current owner keeps the ball unless the opponent is closer by at least the **hand-over margin**.
3. A change only counts once it has persisted for the **minimum dwell**. This is what rejects a touch, a deflection and an aerial duel: those produce one or two frames of proximity, not a sustained one.
4. If the ball is in flight (fast, far from everybody), the team that last had it keeps it.

For frames without a ball observation, the classification from Stage 5 decides: `D` for a dead-ball cause, otherwise the last owner is carried forward. When there is no last owner — the very first frames of a phase — the answer is `X`.

## Stage 7 — Spells

The per-frame owner series is turned into **spells**, because the ranking metric scores spells, not frames:

- **Minimum spell duration** — a run shorter than the minimum is merged into its neighbour (same team ⇒ merge silently; different team ⇒ the shorter one loses).
- **Same-team merging** — a one-frame drop to `D` in the middle of a possession does not split it.
- **Smoothing** — a centred majority vote over a short window removes single-frame jitter without erasing genuine transitions. The window is expressed in seconds.
- **Abstention placement** — `X` is only emitted where we have no defensible owner *and* we are not adjacent to a hand-over. Since the scorer forward-fills `X` with the previous label within a half, an `X` near a hand-over would carry the old label into the new state.

**Why the last rule matters:** on the ranking metric an `X` means "repeat my previous answer". Abstaining is free inside a possession and expensive across a hand-over. So we abstain inside, and guess at hand-overs.

## Stage 8 — Write

The CSV is written with a `frame,label` header, one row per video frame in order, `0 … 199318`, labels in `H A D X`. Floats never appear; the writer emits strings only. The file is written atomically (temp file, then rename) so an interrupted run never leaves a half-written submission.

## Stage 9 — Validate and score

Two separate things, deliberately:

- **Validate** — the official `validate_submission.py` checks, reimplemented in `src/mtah/validate.py` and cross-checked against the official script. A file that fails here is rejected by the scorer, so this gate runs before anything else.
- **Score** — `run_evaluation.py` against the **public 5-minute ground truth**. This is a *correctness* check on alignment and semantics, **never** a tuning signal: the rules forbid using those five minutes to train or tune anything.

The scorer writes per-submission reports — the possession count, the mean spell duration, the fragmentation ratio, the confusion matrix and the transition list — and those numbers, not the public score, are what we tune against.

---

## Where the tuning pressure comes from (and how we resist it)

The only numbers we are allowed to optimise are the ones we can compute ourselves on data we are allowed to use:

| quantity | source | used for |
|---|---|---|
| possession count and mean duration | our own labels | over-segmentation check |
| fragmentation ratio | our own labels | jitter check |
| team possession share | our own labels | sanity against the match (2–1 to Barcelona) |
| `D` duration and count | our own labels | dead-ball classifier check |
| public-window `spellF1` | organisers' 5 minutes | **alignment and semantics only** |

We record every run's report next to the submission so that the final technical document can show the progression honestly.
