# The public five minutes are a check, never a tuning set

The organisers say it, and the four shipped baselines demonstrate it: the variant that wins on the
public window loses on the full match. So the window is used here for exactly what it is for —
to verify that the frames are aligned, and to read what the organisers' labels mean. Two examples
of what that bought us:

* Their `D` is **not** "the ball is not tracked". In the public window the ball is *visible* in
  two thirds of the frames they call dead. That inverted a rule we had already written, and it is
  the single most useful thing the window told us.
* Their possession changes happen when the ball is 2–7 m from the new owner, not when they are
  touching it — which is why a radius gate on its own is too strict.

**No parameter was chosen with reference to those labels.** The control radius, the hand-over
margin and the minimum control span come from an external tuning set (ADR 0008); the merge length
comes from a label-free stability criterion computed on the tracking; the rest are football
statements. The window's role is the one the organisers assigned it: a correctness check.

This is worth stating plainly, because it is the difference between a pipeline and a fit. The
system has no model and no fitted parameters; every number in it is a physical quantity in metres
or seconds, and the configuration that produced the submitted file is in the repository with its
derivation beside it.

Two automatic checks on the whole match, neither of which uses the possession labels:

* **Smart Tagging agreement.** For 284 instances the tagging contains an attacking code and a
  defending code over the *same* interval with *opposite* teams, so the team in possession is
  known. Our labels agree with the tagging on **84.6 %** of the frames of a `BUILD UP` phase and
  **78.9 %** of a `PROGRESSION` phase, and on 61.9 % of transitions, where possession genuinely
  changes.
* **Perturbation stability.** Hide a fifth of the ball observations and recompute: 98 % of
  possessions survive at the shipped merge length, and only 95 % at half that.
