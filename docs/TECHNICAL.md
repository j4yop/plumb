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

**The external tuning set is three matches**, not one: Metrica's `Sample_Game_1` and
`Sample_Game_2` (CSV format, 1,745 and 1,935 events) and `Sample_Game_3` (FIFA/EPTS, 3,620
events), each with an event-derived possession truth. Three games, because the question that
matters is not what wins on one match but whether the value we shipped is the value the geometry
supports on more than one. Each match is read with **its own** half boundaries — the competition
match's windows are meaningless on another match, and applying them marked three thousand
mid-match frames as a warm-up.

Two honest readings from the three-game sweep (`scripts/external_tuning.py`):

- **`control_radius_m = 2.0` is the best on the mean, but only just.** 1.5 m scores 0.3368 and
  2.5 m 0.3338 against 2.0's 0.3389 — all inside the noise of 419–514 possessions. The external
  data does *not* sharply determine the parameter. What it does say is that 2.0 sits on the
  plateau on all three games and 3.5 m does not, and that 2.0 m is the football definition: the
  distance at which a ball is under a player's control rather than merely near them.
- **`min_dwell_frames` has no measurable effect.** 5, 12 and 25 produce *identical* scores on all
  three external games. It is a safety rail against a one-frame blip becoming a hand-over, not a
  tuned parameter, and it is set to half a second because that is the shortest span of control
  that is not a touch.

**A configuration we had shipped earlier was not compliant**, because its merge length had been
chosen by comparing variants on the public five minutes. It was dropped, and the shipped
configuration scores higher on the public window anyway.

The one parameter the external set could not settle, the merge length, is settled instead by a
**label-free criterion on the tracking itself**: hide a fifth of the ball observations, recompute,
and ask how many possessions still exist at the metric's own headline IoU=0.7. Spell survival, on
the provided match and all three external games:

| merge | provided | game 1 | game 2 | game 3 |
|---:|---:|---:|---:|---:|
| 6 | 94.6 % | 95.1 % | 94.8 % | 92.9 % |
| 12 | 96.7 % | 96.5 % | 96.7 % | 95.3 % |
| **25** | **98.2 %** | **98.4 %** | **97.7 %** | **97.6 %** |
| 50 | 98.5 % | 99.6 % | 99.3 % | 99.6 % |
| 100 | 99.2 % | 98.3 % | 98.6 % | 97.6 % |

Below 25 frames, one possession in twenty-five does not survive the tracker blinking, so the
boundaries at that resolution are drawn by noise. From 25 frames up, 98 % of the boundaries survive
on **every one of the four matches** — and past 50 the curve turns over on three of the four,
which is the degenerate direction. The value is the smallest merge length above which the boundary
is geometrically supported, and the reading is identical on four independent matches with no
labels and no video anywhere in the criterion.

As a check that covers the whole match, we used the organisers' own Smart Tagging. For **140**
windows it contains an attacking code and a defending code over the *same* interval with
*opposite* teams, so the team in possession during those intervals is known. Our labels agree with
it on **70.3 %** of the 72,560 frames those windows cover, counting an abstention as wrong — and
77.6 % of the 65,724 frames where we name a team. 85.7 % on `PROGRESSION`, 83.2 % on `BUILD UP`.
The attacking and defending sides of a mirror pair agree to the decimal, which is the strongest
internal consistency check available.

Both denominators are quoted because a system that abstains on the hard frames raises the second
without getting any better. The first is the one to read. That is a full-match check that uses no
possession ground truth and none of the five public minutes.

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

And on the three external matches, where tuning is legal (each read with its own windows):

| game | format | external `spellF1` | external frame accuracy | possessions (truth) |
|---|---|---:|---:|---:|
| `Sample_Game_1` | Metrica CSV | **0.3633** | 0.6723 | 170 (419) |
| `Sample_Game_2` | Metrica CSV | **0.2990** | 0.7261 | 160 (450) |
| `Sample_Game_3` | FIFA/EPTS | **0.3545** | 0.7806 | 198 (514) |

The external `spellF1` is lower than the competition window's because the external reference
counts every touch-chain as a possession — 419 to 514 per match, against the ~200 the
competition's labels imply. The two references define a possession differently, which is why the
merge length is settled by the label-free criterion rather than by either of them (ADR 0008).

**On the whole match** (our own statistics, which are the only ones we may optimise):

- 306 possessions, mean 14.2 s, median and spread reported in `artifacts/run_report.json`.
- Home share of alive time 0.580, against 0.573 in the organisers' labelled window.
- 135 dead-ball spells, 1,950 s of dead time.
- Ball observed on 56.94 % of all frames and 59.31 % of the graded ones.

## 8. The reliability engine, and the claims that rest on it

Everything above is the possession engine. Everything below is what was built on top of it for the
Innovation Challenge, and it is the part that makes the project a *checking* tool rather than a
labelling tool.

### 8.1 The engine

Four per-frame observations, all automatic checks on the provided tracking:

| observation | what it catches |
|---|---|
| `ball_seen` | the ball is not observed at all |
| `ball_stable` | the ball jumped: a re-acquisition is a discontinuity of more than three metres |
| `no_duplicates` | two players of one team inside 1.5 m — the tracker counting one player twice |
| `full_pitch` | fewer than eighteen players visible, which is not what a real match looks like |

Their product is a **support score** per frame. On top of it:

- the **decision margin**, |d_home − d_away|, which says how close the nearest-player call was;
- the **sensitivity**, the share of the scoped frames decided by a margin thinner than a tracking
  error. If a fifth of the frames in a claim were decided by half a metre, then half a metre of
  error moves the answer, and that is a statement about the claim rather than a caveat attached
  to it.

Nothing here is fitted. The thresholds are physical: a re-acquisition is a jump of more than three
metres, two players of one team inside a metre and a half are the same player counted twice, and a
real match has twenty-two players on the pitch.

### 8.2 The scope, and why the zones are placed by the last known ball

A claim is covered by **its own frames**, not by the match's. The scope is the window, the zone,
the tactical phase, or any combination.

One detail makes the difference between a measurement and a tautology. A zone is placed by the
**last observed ball position, carried forward**. Without that, a zone would only ever contain the
frames in which the tracker happened to be working, and its coverage would be 100 % *by
construction* — a circular claim that looks like a perfect one. With it:

| scope | coverage |
|---|---:|
| the whole match | 59.3 % |
| the attacking third | **52.1 %** |
| the `BUILD UP` phases | **92.7 %** |

The final third is materially worse covered than the match, and the build-up phases materially
better. Neither is visible to a global coverage score, and both change what a club should do.

### 8.3 The validation source: the organisers' own annotation

The Smart Tagging is not only set pieces. It is **638 instances over fourteen codes**, and it is
the organisers' own vocabulary for the tactical aspects of the match:

`BUILD UP` · `PROGRESSION` · `CREATING CHANCES` · `LONG BALL` · `ATTACKING TRANSITION` ·
`DEFENSIVE TRANSITION` · `DEFENDING IN MIDDLE THIRD` · `DEFENDING IN DEFENSIVE THIRD` ·
`DEFENDING IN ATTACKING THIRD` · `PLAYERS IN THE BOX` · `BALL IN FINAL THIRD` ·
`BALL IN THE BOX` · `SET PIECES` · `GOALS`

For **140** windows it pairs an attacking code with a defending code over the same interval and
opposite teams — `PROGRESSION` for Barcelona and `DEFENDING IN MIDDLE THIRD` for Athletic Club over
one window. The team named by the attacking code therefore had the ball during that window. That
is a possession statement the organisers made themselves, and it is checkable **without any
possession ground truth**.

| check | result |
|---|---:|
| agreement over the 140 mirror pairs, **every frame in the windows** | **70.3 %** of 72,560 |
| …over the frames where we name a team | 77.6 % of 65,724 |
| agreement on `PROGRESSION` phases | 85.7 % of 30,507 frames |
| agreement on `BUILD UP` phases | 83.2 % of 10,677 frames |
| the attacking and defending sides of a mirror pair | agree to the decimal |
| `Max Players in the box` reproduced **exactly** | **74 of 91** instances |
| `Max Players in the box` reproduced **within one player** | **90 of 91** instances |

The last row needed a measurement rather than a guess. "Max Players in the box" is the
**defending** team's count — its own players in its own penalty area. Counting the tagged team's
players in the box it *attacks* reproduces the organisers' number exactly 16 times out of 91;
counting its players in the box it *defends* reproduces it 74 times out of 91.

This is not tuning against ground truth. The Smart Tagging is provided data, the rules explicitly
allow it as input, and no parameter of the possession engine is fitted to it. The check runs
*after* the labels exist, as a measurement of them.

### 8.4 The claims

Eighteen facts, each a deterministic function of the committed code and the raw tracking, each
carrying a scope, a coverage number, a confidence statement and the frames it rests on. The
tactical ones are keyed to the codes above:

| fact | what it measures |
|---|---|
| `build_up` | line height, options within 20 m of the carrier, how deep the ball is |
| `progression` | how far the ball was carried up the pitch, and the net gain |
| `creating_chances` | entries into the final third and into the penalty area |
| `pressing` | press numbers, closing speed, and whether the press won the ball back |
| `defending_shape` | block width, line height, the biggest gap, the pressure distance |
| `attacking_transition` | what the winning team does with it |
| `defensive_transition` | the counter-press: how often the ball is won straight back |
| `restarts` | set pieces taken, kept, and lost within three seconds |
| `long_ball` | how often the ball was played long |
| `box_presence` | players in the box, against the organisers' own count |

The attack direction is **read from the data**, not assumed: in each half the two teams' players
have a mean x, and the team that spends more of the half in the right half of the pitch is the one
attacking that way. The two teams' means are tens of metres apart, and the reading flips at half
time, as it must.

### 8.5 The refusals and the collection plans

Every refusal carries four things: **why** the data cannot support the question, **what is
missing**, the **remedy**, and the **nearest answerable proxy**. `plumb close-gap` turns a refusal
into a **collection plan** with the gap measured rather than described:

```
    collect   the ball positions for the frames the tracker did not produce
    how much  64,643 frames (40.7% of the graded ones), in blackouts of up to 221.5 seconds
    unlocks   possession inside the blackouts; every other fact in this build already
              stops at the edge of them
    by when   the organisers' corrected tracking export, which repairs the same gaps
```

A refusal without a remedy is a dead end, and the jury reads it as a limitation rather than a
product. This is the piece of work the club takes away.

## 9. Limitations

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
  looks like; another match may differ. The ten-match dataset is what will settle it.
- **The possession share assumes the metadata's team order**, which the organisers document as
  the FIFA/EPTS convention, and which the public window confirms.
- **The tactical shapes are measured on the frames the tracker saw.** A player the tracker has
  lost is not in the shape, and a track slot that has swapped identity would distort it. The
  confidence line on every tactical fact says so.
- **The Smart Tagging is a set of wide priors, not instants.** Its windows are tens of seconds
  long, so the agreement figures above are measured over generous windows and are a lower bound on
  what a precise comparison would give.

## 10. Reproduction

```bash
git clone <this repository> && cd mtah2027
pip install -r requirements.txt
export MTAH_DATA_DIR=/path/to/the/unpacked/bundle
make reproduce        # artifacts/submission.csv
make validate         # the official checks
make test             # 174 tests
```

The repository contains the code, the pinned dependencies and the documentation. It does **not**
contain the match data, which is licensed and not redistributable: `MANIFEST.sha256` carries the
checksums so a reviewer can verify their own download.

Runtime is about three seconds on one core, CPU only, numpy only. There is no randomness
anywhere in the pipeline, so the output is byte-for-byte reproducible. The claims engine adds
about six seconds on top, all of it vectorised and chunked so the peak memory stays under half a
gigabyte.
