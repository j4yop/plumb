# Glossary

The vocabulary of this competition, in the words the organisers use. Definitions only — no implementation, no code. Terms that the challenge defines are marked *(organisers' definition)*; the rest are ours, chosen deliberately because the alternatives are ambiguous.

---

## Match and time

**Frame** — one video frame of the tactical recording. The recording is 25 fps, so 25 frames is one second.

**Video frame** — the frame index that a submission row refers to. Row *i* of the submission is video frame *i*. Frames run `0 … 199318`.

**ATD frame id** — the tracking data's own counter, running `1 … 199319`. It is offset by one from the video frame: `video_frame = frame_id - 1`.

**Phase boundary** — a published division of the video into before the match, the first half, halftime, the second half, and after the final whistle. The two halves are the **graded** phases; the rest is never scored.

**Graded frame** — a frame the organisers score. 158,857 of the 199,319 frames; the two halves only.

**Warm-up** — the period between the end of the first half and the second-half kickoff, when players are on the pitch but the ball is not in play. The second half's graded window opens before its kickoff, so the warm-up contains 2,934 graded frames that are all dead ball.

---

## Tracking and data

**ATD** (Automatic Tracking Data) — the output of Metrica's computer-vision pipeline: the position and speed of every tracked object, once per video frame, including the ball.

**Track slot** — one of the numbered slots in the tracking file (`Track 1 … Track 46`). A slot is *not* a player: slots appear, vanish and swap identity as the tracker loses and re-acquires people. There are no player identifiers anywhere in the data.

**Team membership** — the mapping from track slot to team, read from the ATD metadata. Team-level information is available; person-level information is not.

**Observation** — a value present at a frame. A missing observation is `NaN`, for players and the ball alike.

**Ball observation** — a frame in which the ball's position is present. The ball is observed on 56.9 % of all frames and 59.3 % of graded frames.

**Ball absence** — a frame in which the ball is not observed. Absence has several causes and they are not interchangeable: the ball may be out of play, occluded in a crowd, held by a goalkeeper, off the pitch, or simply lost by the tracker.

**Smart Tagging** — Metrica's automatic tactical annotation: intervals of play and set pieces, each with a code and tags *(organisers' definition)*. Every phase carries a team tag and every set piece is a restart. Thirty-six instances carry no team, including every throw-in.

**Set-piece window** — the time span a Smart Tagging instance covers. It is a window around an event, not the event itself: kick-offs are tagged for five seconds, other set pieces for thirty-five.

**Mirror pair** — two Smart Tagging codes that describe the same interval from the two sides: one attacking, one defending, with the opposite team.

**Homography** — a per-frame 3×3 matrix mapping normalised pitch coordinates to image pixels. `valid` says whether a matrix exists at all; `reprojection_error` says how much to trust it.

---

## The label space

**`H`** — the home team (Barcelona) in possession, the ball alive.
**`A`** — the away team (Athletic Club) in possession, the ball alive.
**`D`** — dead ball: the ball is not in play. Dead-ball *ownership* is deliberately not asked for.
**`X`** — no answer: the system declines to guess, or the frame has no ground truth.

**Abstention** — the deliberate use of `X` on a frame where the system is not confident.

---

## Possession

**Possession** — a maximal run of one team with the ball alive. `H H H A A` is two possessions. `H H D D H H` is two possessions separated by a stoppage, not one.

**Spell** — the interval of a single possession. A spell is the unit the ranking metric scores; a possession *is* a spell.

**Possession change** *(organisers' definition)* — the moment an opposing player gains **controlled** possession of the ball.

**Control** — the state in which one team has the ball: the ball is within the control radius of one of its players and outside that of the other team's. A contested ball (both teams inside the radius) is nobody's control.

**Control episode** — a maximal run of frames in which one team has control. Ownership is decided on episodes, not on frames, because the metric scores possessions and a frame-level decision shatters them.

**Absence class** — why the ball is missing on a given frame: out of play, a stoppage, a warm-up, or an occlusion. They are not interchangeable: an occlusion during live play is still somebody's possession.

**Controlled possession** — possession that is not merely a touch: not a touch without control, not a deflection of a pass that does not intercept it, not an aerial duel won without subsequent control. The organisers are explicit that these do **not** change possession.

**Handover** — the boundary between two spells of different teams.

**Stoppage** — a period in which the ball is not in play. A stoppage is not a possession; it interrupts one.

**Loose ball** — a phase in which the ball is contested or in flight. Possession stays with the last team that had it.

---

## Our measurement vocabulary (Phase 2 project)

**Coverage** — how much of a match the tracking actually supports. A frame is covered for the ball when the ball is observed; a phase is covered when the evidence needed for the claims made about it is present.

**Unrecoverable gap** — a stretch of frames where the evidence needed does not exist and cannot be reconstructed. Not every absence is a gap: an absence during a stoppage is informative, and an absence during a live attack is a gap.

**Confidence band** — the interval within which a computed fact is asserted to be true, derived from how much of the underlying tracking was observed.

**Verified fact** — a deterministic computation over the tracking, carrying its evidence frames, its coverage basis and its confidence band.

**Capability map** — the set of questions a given match's tracking can answer, and the confidence with which each can be answered.
