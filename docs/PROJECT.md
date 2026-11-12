# The project — name, thesis, and what Phase 2 has to earn

## The name

> **Certifying Football Claims From Incomplete Tracking**
>
> `certifying-football-claims-from-incomplete-tracking`

Chosen by a five-advisor council with an anonymous peer-review round (the working is in
`research/`). Six alternatives were rejected on the record:

| Rejected | Why |
|---|---|
| *Admissible Possession: What Tracking Can Support* | "Admissible" presupposes an external adjudicator — a standard, a certifier, someone who can overrule. We have none: the authority is **self-certification with the evidence carried**. And it names possession, which is what Phase 1 already did; the Phase 2 project has to be visibly more than a possession labeller with a confidence score. |
| *An Admissibility Test for Football Metrics* | Same courtroom problem, and a "test" sounds like a benchmark rather than a product a club would run. |
| *Metrics That Survive Football Tracking Gaps* | States the thesis plainly, but "survive" is vague and it never names the refusal. |
| *Certifying Possession Across Tracking Blind Spots* | Accurate, but possession again — Phase 1 twice. |
| *Warranted Football Metrics From Incomplete Tracking* | "Warranted" is stiff and "metrics" plural overpromises the scope. |
| *What the Frames Will Support* | Memorable, but it is a sentence rather than a name, and it says nothing about what the tool is for. |

**One line:** *It tells you which of your football metrics your tracking can actually stand behind —
and refuses the ones it cannot.*

**The unit of output** is a **claim**: a number, the frames it rests on, the coverage behind it, and
a confidence band. Where the coverage does not support the claim, the system says so, names what
is missing, and says what would close the gap.

**Who it is for:** the analyst who has to defend a number in a room. Not the data scientist, and
not the chat interface. The system is a colleague that says "you can say that", not one that
generates more numbers to argue about.

## The thesis

Clubs already have tracking and event data. What they do not have is **grounds**: a way of
knowing which of the numbers derived from it survive the gaps in the feed — the 41 % of frames
where the ball is invisible, the tracklets that swap identity, the players that are counted twice,
the windows where nothing can be said at all.

The competition's own data is the perfect adversarial case: the ball is missing on 40.69 % of the
graded frames, there are no player identities, and the ground truth we are scored against is
private and corrected in ways we cannot see.

## What Phase 2 has to earn

The name is a promise. Three things have to be true by 14 January, and each has a kill criterion.

1. **Refusal must be claim-scoped, not global.** Coverage has to be computed over the *conditions
   of the claim* — the zone, the phase, the time window, the teams — not over the match as a
   whole. A global coverage score makes every refusal arbitrary and the jury hears Phase 1
   twice: a possession labeller with a confidence number.
   *Kill:* if a claim-scoped coverage model cannot be validated against organiser-provided
   annotations on the 10-match dataset, the project changes shape.

2. **Every claim must carry its own evidence.** Frames, tracking quality for those frames, the
   context, and a confidence band — in one machine-readable packet that a renderer consumes, so
   that no language model ever writes a claim.
   *Kill:* any fact that cannot be reproduced from the raw tracking by the committed code is
   dropped, however good it looked.

3. **Every refusal must carry a remedy.** "The data cannot support this" is half an answer. The
   other half is "3 of 8 matches lack that zone; go and collect it" — a gap in the data becomes a
   piece of work for the club.
   *Kill:* a refusal with no remedy is a dead end, and the jury will read it as a limitation
   rather than a product.

## The build order

```
  reliability engine  →  verified fact library  →  the ledger  →  the interface
  (coverage, gaps,     (40-ish deterministic      (metric |      (local intent routing,
   in-silico error      claims, each with its      coverage |     deterministic rendering,
   injection)           evidence and confidence)   certified |   deterministic refusal gate)
                                                refused |
                                                evidence frames)
```

The **ledger** is the artefact that matters: one row per claim, with what it rests on. It is
readable by a human, checkable by a script, and it is the thing a club would actually take away.

## The naming council, on the record

- Five advisors, each naming independently, then an anonymous peer-review round.
- **Unanimous on the demo format:** a live CLI on the organisers' own laptop, not a web app, a
  deployed notebook, or a video. See [`DEMO.md`](DEMO.md).
- **Unanimous on the demonstration order after the review:** answer first, refusal second, coverage
  and remedy third. Opening with "our data is 41 % broken" anchors the jury on our weakness.
- **Unanimous on the failure mode to avoid:** a name centred on "AI" or on "insights". The jury
  discounted "AI-powered" and "next-gen" in 2026 on sight, and so will we.
