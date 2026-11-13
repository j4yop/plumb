# The organisers' own annotation is the validation source

## The decision

The Phase-2 reliability engine needs a way to be **wrong in a way we can see**. Without one, the
engine is a set of thresholds with no way of knowing whether they are right.

The obvious candidate is the possession ground truth, and it is forbidden: the clarification email
says we must not *"train, fit or calibrate"* on it.

The answer turned out to be in the bundle already, and it was hiding in plain sight.

## What the Smart Tagging actually is

Not set pieces. **638 instances over fourteen codes**, each with a team, a half, and sometimes a
measurement:

| code | n | what it marks |
|---|---:|---|
| `PLAYERS IN THE BOX` | 97 | players in the penalty area, **and how many** |
| `BALL IN FINAL THIRD` | 93 | the ball in the final third |
| `BALL IN THE BOX` | 72 | the ball in the penalty area |
| `PROGRESSION` | 66 | the team moving the ball up the pitch |
| `DEFENDING IN MIDDLE THIRD` | 66 | the team defending in the middle third |
| `SET PIECES` | 59 | a restart, with its type |
| `CREATING CHANCES` | 30 | the team in the attacking third |
| `DEFENDING IN DEFENSIVE THIRD` | 30 | the team defending in their own third |
| `LONG BALL` | 29 | the team going long |
| `ATTACKING TRANSITION` | 24 | a team winning the ball and going forward |
| `DEFENSIVE TRANSITION` | 24 | the other side reacting to it |
| `BUILD UP` | 22 | the team playing the ball out of defence |
| `DEFENDING IN ATTACKING THIRD` | 22 | the team defending in the opponent's third |
| `GOALS` | 4 | a goal |

Three properties make this the validation source.

**It is the organisers' own vocabulary for the tactical aspects.** The Innovation Challenge asks
for an aspect; the aspects they have in mind are these codes. A system that answers in their
vocabulary can be checked against their annotation.

**It comes in mirror pairs.** For 140 windows there is an attacking code and a defending code over
the *same* interval with *opposite* teams — `PROGRESSION` for Barcelona and
`DEFENDING IN MIDDLE THIRD` for Athletic Club over one window. The team named by the attacking
code therefore had the ball during that window. That is a possession statement **the organisers
made themselves**, and checking our labels against it uses no possession ground truth at all.

**It carries measurements, not just labels.** `Max Players in the box` is a number the organisers
wrote down, so we can count the same thing from the tracking and compare.

## The consequence

**Our possession labels agree with the organisers' own phase annotation on 77.6 % of the frames
covered by 140 mirror pairs** — 85.7 % on progressions, 83.2 % on build-ups, and the attacking and
defending sides of the same mirror pair agreeing to the decimal, which is the strongest internal
consistency check available.

And the sharpest check of all needs no possession labels at all: we reproduce the organisers' own
`Max Players in the box` count **exactly in 74 of 91 tagged instances, and within one player in
90**. It is a count of players inside a rectangle, checked against a number they wrote down.

Reading that annotation correctly took a measurement rather than a guess. "Max Players in the box"
is the **defending** team's count — its own players in its own penalty area. Counting the tagged
team's players in the box it *attacks* reproduces the organisers' number exactly 16 times out of
91; counting its players in the box it *defends* reproduces it 74 times out of 91. The first
reading is the natural one and it is wrong; the measurement is what settled it.

## What this is not

This is **not** tuning against ground truth, and the distinction matters:

- the Smart Tagging is *provided data*, and the rules explicitly allow it as input;
- it is *not* possession ground truth, and no parameter of the possession engine is fitted to it;
- the possession engine's thresholds come from the external tuning set and the label-free
  stability criterion (ADR 0008), and they are **unchanged** by any of this;
- the check runs *after* the labels exist, as a measurement of them, not as a source of them.

The rule the project has held to throughout is the one the organisers wrote: *the possession labels
and the video are out; the tracking, the smart tagging and external datasets are in.* This ADR
stays inside that line.
