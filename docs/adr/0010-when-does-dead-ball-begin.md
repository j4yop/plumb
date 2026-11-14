# When does the dead period begin?

## The question

The organisers' clarification email asks it outright, and it is the only question in that email
that could change the model:

> *"For a stoppage, does `D` begin at the infringement, at the whistle, or at the tracking's own
> flag?"*

The ground truth is built from the organisers' **corrected** tracking, whose dead-ball flag is not
in the bundle. So the onset has to be inferred from what we can see, and the answer has to be
applied quickly — the submission deadline is four days after the email went out.

## The decision

**Implement the onset as a configuration value, and measure the three rules we can implement,
rather than waiting to be told.**

`Config.dead_onset` takes one of three values:

| value | the dead period begins when… | closest to |
|---|---|---|
| `movement` (the default) | the ball is not tracked **and** the players have stopped | the whistle |
| `ball_out` | the ball's last observed position is outside the pitch | the ball leaving play |
| `earliest` | either of those fires | the infringement |

The third option the organisers mention — *the tracking's own flag* — is the corrected tracking,
which is not in the bundle. If that is the answer, the honest response is to ask for the export
rather than to guess at it.

The default stays `movement`, so nothing about the submitted file changes while we wait.

## What the three rules actually cost

`scripts/dead_onset.py`, measured on the whole match, against a **legal** reference — the Smart
Tagging's 140 mirror pairs, which state who had the ball without any possession ground truth:

| rule | possessions | mean length | dead frames | mirror-pair agreement |
|---|---:|---:|---:|---:|
| `movement` (default) | 306 | 14.2 s | 48,755 (30.7 %) | **77.6 %** |
| `earliest` | 305 | 14.1 s | 49,875 (31.4 %) | 77.4 % |
| `ball_out` | 206 | 29.2 s | 8,530 (5.4 %) | 75.6 % |

And on the public five minutes, for information only and never for selection:

| rule | macroF1 | spellF1 | possessions |
|---|---:|---:|---:|
| `movement` (default) | 0.6878 | **0.5000** | 15 |
| `earliest` | 0.6878 | **0.5000** | 15 |
| `ball_out` | 0.5284 | 0.4903 | 14 |

## The bug this section used to contain

The first version of the rule had `ball_out` and `earliest` as byte-identical branches. Both
meant "out of play **or** the players stopped", so the table showed them agreeing on every
figure and the test asserted that all three rules found a stoppage — **the test was asserting
the bug**.

The three rules are now genuinely distinct, and the distinction is informative. `ball_out` on its
own marks only **5.4 %** of the match dead, because most stoppages are not the ball leaving the
pitch — the tracker simply loses it while the players stand still. That is why it scores worse
than the other two: the missing frames then carry possession forward and the spells run to a mean
of 29.2 s.

So the data answers the organisers' question even though the organisers did not. A rule keyed
only to the ball leaving play recovers a sixth of the dead time the match visibly contains, so it
cannot be the rule the ground truth uses. The onset that fits is the one that waits for the
players to stop — which is what the shipped default does, and what `earliest` reduces to in
practice (the two differ by 1,120 frames and one possession).

## The conclusion, and why it matters

**The answer cannot hurt us.** The three rules differ by one possession over a whole match, by
0.7 percentage points of dead-ball share, and by 0.2 points of agreement with the organisers'
own annotation — and by nothing at all on the public window.

That is worth knowing before the reply arrives, because it means the pending question is not a
pending *risk*. It is a pending *label*, and the model's behaviour under every possible answer
has already been measured.

It is also the honest summary of what the dead-ball layer is: a rule that waits for the players
to stop, and that costs very little whichever moment is chosen, because the moments are the same
moments. The expensive mistake in this layer was never the onset. It is a **false** dead period —
one that splits a real possession in two — and the rule is deliberately conservative about that
(ADR 0002).

## What this does not do

It does not decide the question. The default is unchanged, the submission is byte-identical, and
when the answer arrives it is one edit to `src/mtah/config.py` and a re-run.
