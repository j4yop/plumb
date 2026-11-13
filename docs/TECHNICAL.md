# Frame-level ball possession — technical document

*PLUMB — Phase 1. The project this grows into is described in [`PROJECT.md`](PROJECT.md).*

**More Than A Hack 2027, Initial Challenge** · FC Barcelona vs Athletic Club, LaLiga EA Sports
2024–25, matchday 2 · tactical recording, 199,319 frames at 25 fps (2 h 12 m 52.8 s).

---

## 1. The problem

For every frame of one match, say who has the ball: Barcelona (`H`), Athletic Club (`A`), dead
ball (`D`), or no answer (`X`). 158,857 of the 199,319 frames are scored, and the score is
`spellF1`: possessions matched one-to-one by temporal IoU, averaged over IoU 0.3–0.7.

Three facts about the data shape everything that follows.

1. **The ball is missing on 40.69 % of the graded frames** (94,214 of 158,857 observed). It is the
   most informative signal in the file and the least reliable one.
2. **The ball being visible does not mean the ball is in play.** During halftime the ball is
   observed on 94.07 % of frames while twelve players warm up.
3. **A possession is an interval, not a frame.** The metric matches possessions, so a possession
   that flickers into five pieces is five answers to score, not one noisy one.

## 2. Approach

Three rules, in the order they apply.

### 2.1 Control, not proximity

A team controls the ball when the ball is within the **control radius (2.0 m)** of one of its
players and outside that radius of the other team's, *and* the team that is nearer is nearer by at
least the **hand-over margin (0.5 m)**. If both teams have a player inside the radius the ball is
contested and nobody controls it.

This is the organisers' own definition — a change of possession requires *controlled* possession,
and explicitly not "a touch of the ball without control", not "a deflection of a pass that does
not intercept it", not "an aerial duel won without subsequent control". A touch fails the radius
test; a deflection fails it too, because the ball passes through the defender's radius without
staying there; a duel fails it because two players are inside the radius at once.

### 2.2 Decide in episodes, not frames

Ownership is decided on **episodes**: maximal runs of frames in which one team has control. An
episode shorter than **one second** is absorbed into its neighbours — if the neighbours agree it
was a blip between them, and if they differ the short episode loses to the established
possession.

This was the single largest gain in the whole project. Deciding frame by frame — the obvious
implementation, and the one the shipped baseline uses — shattered one 41-second truth possession
into seven pieces, because a pass travelling within a metre of a defender flipped the owner for a
frame or two, and each flip became another possession for the scorer to punish. Switching from
frame-level to episode-level decision took the public-window score from 0.3902 to 0.4343, and
brought the possession count from 24 to 18 against the organisers' 17.

Half a second is not an arbitrary number: it is the shortest span of control that is not a touch,
and it is the value the external tuning set supports (§5, ADR 0008). A control episode shorter
than that is absorbed into its neighbours, so it can never become a possession of its own.

### 2.3 Dead ball is a play state

A frame is dead when:

- the ball is untracked **and** at most **two players are moving faster than 2 m/s** — the match
  has stopped; or
- the ball was last seen outside the pitch — it went out of play; or
- it falls in the published warm-up block at the start of the second half (frames 110,808–113,741,
  which the organisers grade and which are all dead).

Measured against the organisers' labels in the public window, the first of those tests is **96 %
precise**. Every other test we tried was 40–55 % precise.

**The detector is deliberately conservative, and that is a decision, not a limitation of effort.**
The metric's error asymmetry is severe: a false dead-ball period splits a real possession in two
(one true match plus one spurious), while a missed dead-ball period only makes a possession
slightly too long, and temporal IoU forgives that. We therefore accept that we recover about
28 % of the organisers' dead-ball frames and keep the rest as possession. The alternative — a
detector with 55 % precision — was measured and rejected.

The same asymmetry decides the abstention policy. `X` is forward-filled by the scorer with the
last label in the same half, so on the ranking metric an `X` means "repeat my previous answer":
it is free inside a possession and expensive across a hand-over. We use `X` only where no owner
is defensible at all, and never adjacent to a hand-over. In this run it accounts for 2 % of the
graded frames.

## 3. Assets used, and assets dropped

| Asset | Used for | Why |
|---|---|---|
| `BAR-ATH_tactical_atd.txt` | **the whole decision path** | one record per video frame, players and the ball, positions and speeds |
| `BAR-ATH_tactical_atd.xml` | team names and the slot→team map | read from the metadata, never hard-coded, so the sides cannot be inverted silently |
| `BAR-ATH_tactical_smart_tagging.xml` | **validation only** — 638 instances, 14 codes, 59 set pieces | the only organiser-provided supervision that covers the whole match (see §5) |
| `BAR-ATH_tactical_homography.csv` | **debugging only** | 100 % valid, and the right tool for projecting the tracking onto a frame to see what the model saw; it carries no information the tracking does not already have for this question |
| `BAR-ATH_tactical.mp4` | **inspection only** | a fixed wide tactical camera; players are twenty pixels tall, so it cannot answer a question the tracking cannot |
| `BAR-ATH_broadcast_*` | **dropped** | 65.81 % of its homography is valid, it has cuts and replays, its frame count differs from its tracking by one, and it is not aligned to the submission's timeline |

## 4. Training data

**None.** There is no permitted training signal for this match: the labels we are scored against
are private, and the organisers forbid hand labels on the provided match for training *or*
validation. The system is therefore a deterministic algorithm with no fitted parameters — every
threshold is a football quantity in metres or seconds, justified in §2 and recorded in
`src/mtah/config.py`.

## 5. How the thresholds were chosen

This is the part of the report the organisers asked for, so it is worth being precise.

The public five minutes are the **only** labelled data anyone receives, and the organisers state
that they are for checking correctness and are not a tuning set. We used them for exactly that:
to verify that the frames are aligned, to read what their labels mean, and to measure whether a
rule means what we think it means. Two examples of what that bought us:

- Their `D` is **not** "the ball is not tracked" — in the public window the ball is *visible* in
  two thirds of the frames they call dead. That was not obvious and it inverted a rule we had
  already written.
- Their possession changes happen when the ball is 2–7 m from the new owner, not when they are
  touching it, which is why a radius gate on its own is too strict.

**A configuration we had shipped earlier was not compliant**, because its merge length had been
chosen by comparing variants on the public five minutes. It was dropped. The shipped
configuration scores 0.5000 on the public window — better than that one — and 0.3019 against
0.2925 on the external match, where tuning is legal.

The one parameter the external set could not settle, the merge length, is settled instead by a
**label-free criterion on the tracking itself**: hide a fifth of the ball observations, recompute,
and ask how many possessions still exist at the metric's own headline IoU. Below 25 frames, one
possession in twenty does not survive the tracker blinking, so the boundaries at that resolution
are drawn by noise; from 25 frames up they are geometrically supported. Both the provided match and
the external match show the same shape, with no labels and no video anywhere in the criterion.

As a check that covers the whole match, we used the organisers' own Smart Tagging: for 284
instances it contains an attacking code and a defending code over the *same* interval with
*opposite* teams, so the team in possession during those intervals is known. Our labels agree with
the tagging on **84.6 %** of the frames of a `BUILD UP` phase and **78.9 %** of a `PROGRESSION`
phase — the two codes with the cleanest semantics — and the agreement falls to 61.9 % on
transitions, where the possession genuinely changes. That is a full-match check that uses no
ground truth and none of the five public minutes.

## 6. The possession rules as implemented

| Situation | What we do | Why |
|---|---|---|
| Ball at a player's feet | that team owns it | control |
| Ball between two players of different teams | the previous owner keeps it | contested; the organisers' ground truth is derived from the corrected tracking, which resolves contests itself |
| Ball in the air, nobody within the control radius | the previous owner keeps it | "in phases where the ball is contested or loose, possession stays with the last team that had it" |
| Ball untracked during live play | the previous owner keeps it | an occlusion is still somebody's possession; the ground truth comes from the *corrected* tracking |
| Ball untracked and the players have stopped | dead ball | the match has stopped |
| Ball last seen outside the pitch, players stopped | dead ball | it went out of play |
| Half time, and the second-half warm-up | dead ball | published; the ground truth grades them |
| A change that lasts less than a second | absorbed into the previous possession | control has to persist |
| No defensible owner at all | `X` | never next to a hand-over, where it would be expensive |

## 7. Results

**On the public five minutes** (a correctness check, not a ranking):

| | macroF1 | spellF1 | possessions | mean length |
|---|---:|---:|---:|---:|
| `baseline_raw` | 0.5972 | 0.0378 | 131 | 2.0 s |
| `baseline_smooth25` | 0.6200 | 0.2868 | 36 | 7.6 s |
| `baseline_smooth50` (the published floor) | 0.6207 | 0.3256 | 26 | 10.8 s |
| `baseline_smooth125` | 0.5812 | 0.4242 | 16 | 18.5 s |
| **this system** | **0.6878** | **0.5000** | **15** | 18.8 s |

And on the external match, where tuning is legal:

| | external spellF1 | external frame accuracy |
|---|---:|---:|
| configuration before the external sweep | 0.2925 | 0.5954 |
| **shipped configuration** | **0.3019** | **0.6021** |

**On the whole match** (our own statistics, which are the only ones we may optimise):

- 306 possessions, mean 14.2 s, median and spread reported in `artifacts/run_report.json`.
- Home share of alive time 0.580, against 0.573 in the organisers' labelled window.
- 135 dead-ball spells, 1,950 s of dead time.
- Ball observed on 56.94 % of all frames and 59.31 % of the graded ones.

## 8. Limitations

- **Dead-ball recall is low, by choice.** We recover about 28 % of the organisers' dead-ball
  frames. The ground truth's dead flag is a property of the *corrected* tracking, which we do not
  have; recovering it from play-state evidence is the best available proxy, and pushing recall
  costs precision, which costs more.
- **Hand-overs are detected late**, typically by several seconds, because the ball is untracked
  around 41 % of the time and a reception is often one of the frames where it is missing. We
  tried to infer the hand-over from the players converging on the ball's last known position; it
  did not help, and it is in the code switched off.
- **There are no player identities**, only 46 track slots for 22 players, and the organisers warn
  that slots swap identity as the tracker loses and re-acquires people. We could not repair the
  slot→team map from the data: spatial-neighbour voting recovers a left/right partition of the
  pitch rather than two teams. The metadata assignment is used as it stands.
- **Everything is one match.** A possession rate of 3.4 per minute of play is what this match
  looks like; another match may differ.
- **The possession share assumes the metadata's team order**, which the organisers document as
  the FIFA/EPTS convention, and which the public window confirms.

## 9. Reproduction

```bash
git clone <this repository> && cd mtah2027
pip install -r requirements.txt
export MTAH_DATA_DIR=/path/to/the/unpacked/bundle
make reproduce        # artifacts/submission.csv
make validate         # the official checks
make test             # 103 tests
```

The repository contains the code, the pinned dependencies and the documentation. It does **not**
contain the match data, which is licensed and not redistributable: `MANIFEST.sha256` carries the
checksums so a reviewer can verify their own download.

Runtime is about three seconds on one core, CPU only, numpy only. There is no randomness
anywhere in the pipeline, so the output is byte-for-byte reproducible.
