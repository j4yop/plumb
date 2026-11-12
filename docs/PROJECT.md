# The project — name, thesis, and what Phase 2 has to earn

## The name

> # PLUMB
>
> *to plumb* — to sound the depth of something, to find out where it actually stands.

**One word, five letters.** `plumb` on GitHub, `plumb` on the slide, `plumb ask` at the terminal.

**The one line, pinned as the README's first sentence:**

> *plumb is a local, deterministic checker of tracking-derived claims: it supports a claim, or refuses
> it with the reason and what would have to be collected. It does not predict, it does not resolve
> identity, and it sends nothing anywhere.*

**Why this word.** It names the **act of checking**, which is the one thing both phases of this
project share — a possession engine that certifies what the tracking supports in Phase 1, and a
claims engine that does the same for every other tracking-derived metric in Phase 2. A name locked
to possession dies the day the ten-match dataset lands; a name locked to "metrics" sounds like a
dashboard registry. "Plumb" is an **instrument, not a verdict**: the tool supports or refuses, and
the brand never carries a certification the system does not give. It is also the verb the interface
uses — you *plumb* a claim.

## The council record

Five advisors, each naming independently; then an anonymous peer-review round. Twenty-five
candidates. The eliminations that decided it:

| Cut | Why |
|---|---|
| **Caveat** (6) | The strongest runner-up — operations staff already say "the caveat on that xG" — but it is owned in the juror's world (DEF CON Caveat, a PyPI package of the same name), and it names the *warning* rather than the *check*. The brand would cover only the wounded half of the output. |
| **Fathom** (6) | Fathom Analytics is a live product, and the verb means *to understand* — the opposite of the beat. |
| **Warrant** (6) | A legal authorisation finding; heard once as "warranty". |
| **Trace** (5) | Four advisors proposed it, but it is ubiquitous in software (Jaeger, Zipkin, OpenTelemetry) and unsearchable as a slug. |
| **Sieve** (5) | An RFC number, and a sieve discards silently — ours returns what it caught. |
| **Quorum** (6) | A consensus verdict, and a law firm. |
| **Bound** (5) | Heard as "round", and it names a limit rather than a check. |
| **Ground** (6) | Leaks *ground truth*, which the system explicitly cannot deliver. |
| **Vouch** (5) | Binary — the project issues graded confidence, not a yes — and "vouching for" is testimonial register. |
| **Plumb** (5) | **Survives.** An instrument, not a verdict. No collision in this world. "True plumb" means exact, which is the register the project wants. Its only hazard is "plumber", which is a joke, not a confusion. |

**Unanimous across the council, on the demonstration format:** a live CLI on the organisers' own
laptop — not a web app, not a deployed notebook, not a video. See [`DEMO.md`](DEMO.md).

## The thesis

Clubs already have tracking and event data. What they do not have is **grounds**: a way of
knowing which of the numbers derived from it survive the gaps in the feed — the 41 % of frames
where the ball is invisible, the tracklets that swap identity, the players that are counted twice,
the windows where nothing can honestly be said at all.

The competition's own data is the perfect adversarial case: the ball is missing on 40.69 % of the
graded frames, there are no player identities, and the ground truth we are scored against is
private and corrected in ways we cannot see.

## What Phase 2 has to earn

The name is a promise. Three things must be true by 14 January, and each has a kill criterion.

1. **Refusal must be claim-scoped, not global.** Coverage has to be computed over the *conditions
   of the claim* — the zone, the phase, the time window, the teams — not over the match as a
   whole. A global coverage score makes every refusal arbitrary, and the jury hears Phase 1
   twice: a possession labeller with a confidence number.
   *Kill:* if a claim-scoped coverage model cannot be validated against organiser-provided
   annotations on the ten-match dataset, the project changes shape.

2. **Every claim must carry its own evidence.** Frames, tracking quality for those frames, the
   context, and a confidence band — in one machine-readable packet that a renderer consumes, so
   that no language model ever writes a claim.
   *Kill:* any fact that cannot be reproduced from the raw tracking by the committed code is
   dropped, however good it looked.

3. **Every refusal must carry a remedy.** "The data cannot support this" is half an answer. The
   other half is "three of eight matches lack that zone; go and collect it" — a gap in the data
   becomes a piece of work for the club.
   *Kill:* a refusal with no remedy is a dead end, and the jury reads it as a limitation rather
   than a product.

## The build order

```
  reliability engine  →  verified fact library  →  the ledger  →  the interface
  (coverage, gaps,     (deterministic claims,      (metric |     (local intent routing,
   in-silico error      each with its evidence,     coverage |    deterministic rendering,
   injection)           coverage and confidence)    supported |  deterministic refusal gate)
                                                refused |
                                                evidence frames)
```

The **ledger** is the artefact that matters: one row per claim, with what it rests on. Readable
by a human, checkable by a script, and the thing a club would actually take away.

## The interface

```
plumb ask "<question>"        # the answer, with its evidence
plumb ask --json "<question>" # the same, machine-readable
plumb coverage --window ...   # what the tracking can and cannot carry
plumb why "<question>"        # why the answer holds, or why it cannot
plumb close-gap "<question>"  # what would have to be collected to answer it
plumb ledger                  # metric | coverage | supported or refused | evidence frames
```
