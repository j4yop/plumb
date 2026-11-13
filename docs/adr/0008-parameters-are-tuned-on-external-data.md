# The thresholds are tuned on external data, never on the possession labels

The organisers' clarification email draws three lines:

> **not allowed** — "Checking your output against the video." · "Hand labels, human-produced data
> or any other data created manually on the provided game." · "Uploading the provided data to AI
> services." · "Training, fitting or calibrating your algorithm on the ground-truth possession data
> or on the provided video."
>
> **allowed** — "Running automatic checks using only the provided data." · "Inspecting the provided
> data and the video to better understand what counts as possession." · "Using as input the video,
> the automatic tracking data, the smart tagging or any other generated data, as long as your
> algorithm was not trained on the ground truth or on the provided video." · "Using any dataset you
> have the rights to use."

Read carefully, the prohibition is narrow and precise: **the possession labels and the video are
out; the tracking data, the smart tagging and external datasets are in.** That gives three routes
for a parameter, and we use all three.

| Parameter | Value | Route | Uses the possession labels? |
|---|---:|---|---|
| `control_radius_m` | **2.0** | external labelled sweep: two metres beat two and a half by 16 % relative on the external match's own possession spells, and two metres is where a ball is under a player's control rather than merely in their half-metre | no |
| `handover_margin_m` | **0.5** | external sweep is flat; the football statement is that the opponent must be clearly closer | no |
| `min_dwell_frames` | **12** (0.5 s) | external sweep; half a second of control is the shortest that is not a touch | no |
| `min_control_frames` | **25** (1 s) | **label-free stability lower bound**, below | no |
| `min_spell_frames` | **25** (1 s) | a football prior — a possession shorter than a second is not a possession; the external sweep is flat over 12–50 | no |
| `dead_movers` | **2** | the physical definition — a stoppage is a match in which nobody is running; deliberately on the conservative side (ADR 0002) | no |

## The external tuning set

`scripts/external_tuning.py` builds it from **Metrica Sports' own public sample data**
(https://github.com/metrica-sports/sample-data — "if you use it for anything public, please
acknowledge the source"). Sample Game 3 is in the same FIFA/EPTS format as the competition
bundle and carries 3,620 frame-accurate event annotations, enough to derive a possession ground
truth for a match we are allowed to tune on. Two things had to be built to use it: the tracking
columns are *not* in the metadata's file order (the metadata lists 35 players, the tracking has 22
on-pitch columns), so the columns are assigned to teams by voting each event for the column
nearest to it; and the event annotations carry no dead-ball class at all, so the dead layer is
switched off for the comparison (`dead_detection`) — otherwise we would be scoring two definitions
against each other rather than the parameters.

## The label-free stability criterion

One parameter could not be settled by the external set, because the two references define a
possession differently: the external reference counts short touch-chains (514 possessions, mean
9.5 s) while the competition's counts longer ones, so a merge threshold tuned to reproduce one
reference's granularity is mis-set for the other. Fitting it to either set's labels would be
fitting to ground truth.

So it is settled from the **geometry alone**, using only the tracking:

> **Perturbation stability.** Hide 20 % of the ball observations at random, recompute the
> possession sequence, and ask how many possessions still exist at the metric's own headline IoU.
> A merge length that the geometry supports gives the same answer whether the tracker blinked or
> not; one that is fitting noise gives a different answer every time.

| merge | spell survival, provided match | spell survival, external match |
|---:|---:|---:|
| 6 frames | 94.6 % | 92.9 % |
| 12 frames | 96.7 % | 95.3 % |
| **25 frames** | **98.2 %** | **97.6 %** |
| 50 frames | 98.5 % | 99.6 % |
| 100 frames | 99.2 % | 97.6 % |

The reading is a **lower bound**, not a maximum: below 25 frames, one possession in twenty does
not survive the tracker blinking, so the boundaries at that resolution are being drawn by noise;
from 25 frames up, the boundaries are geometrically supported. (Beyond 25 the survival keeps
rising on the provided match, but that direction is degenerate — fewer, longer possessions are
trivially more stable — and the external match collapses at 100 frames.) Both matches, the same
shape, no labels and no video anywhere in the criterion.

## What this cost, honestly

An earlier configuration had a merge length chosen by comparing variants **on the public five
minutes**, which is what the email forbids. It scored 0.4824 there against this one's 0.5000, so
dropping it cost nothing on the window — but the external set would have preferred a different
merge length, and the reason it does not apply is the definitional difference described above.
The point is not the score. The point is that no number in this system was chosen with reference
to the possession labels of the provided match, and that is checkable: `scripts/external_tuning.py`
and `scripts/stability_sweep.py` are in the repository, and the configuration in
`src/mtah/config.py` carries the derivation next to each value.
