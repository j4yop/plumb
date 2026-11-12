# The set-piece prior does not pay for itself

Dead ball is detected conservatively — the ball is untracked and almost nobody is running — and
that test is 96 % precise but recovers only about 28 % of the organisers' dead-ball frames. The
obvious way to raise the recall is to use the organisers' own Smart Tagging: 59 set-piece windows
mark the restarts, and a restart is dead ball by definition.

Measured on the public window, the prior does raise the recall, and it costs more than it earns:

| Rule | Precision | Recall |
|---|---:|---:|
| ball untracked and ≤2 players moving (what we ship) | **0.957** | 0.273 |
| + ball unattended near a boundary, inside a set-piece window | 0.851 | 0.292 |
| + ball unattended inside a set-piece window | 0.792 | 0.321 |
| + any unattended frame inside a set-piece window | 0.732 | 0.440 |

The second row buys 28 additional true dead-ball frames for 57 additional false ones. A false
dead-ball frame is the expensive kind: it splits a real possession, so it costs a true match *and*
adds a spurious possession, while a missed dead-ball frame only makes a possession slightly too
long — and temporal IoU forgives that.

So the prior stays off. What the experiment does establish is the shape of the remaining headroom,
and it is the shape the Phase 2 project is built for: **the dead-ball question is not a threshold
problem, it is a coverage problem.** The honest answer to "is the ball dead here?" is not a
label but a measurement — how much of the window can this feed carry, and what would have to be
collected to answer the question properly. That is what `plumb coverage` and `plumb close-gap` are
for.
