# How this is shown to the judges

**Decision, from the naming council's unanimous recommendation plus the peer-review edits:** a
**live CLI run on the organisers' own laptop**, framed by four slides, with a recorded terminal
session committed to the repository as the fallback.

Rejected, and why:

| Rejected | Why |
|---|---|
| A live web app | It implies a deployable product and a data-transfer story, which contradicts the one thing the pitch is selling: the data never leaves the machine. It also buys cosmetic legibility with real build and failure surface. |
| A deployed notebook | Slow in front of a jury, read-only, and it puts the jury in the code rather than in the decision. |
| A pre-recorded video | The jury discounts it, and the refusal has to be seen *happening*. |
| A slide deck as the artefact | It cannot show determinism, and it cannot answer a question asked in the room. |

## The command surface

Not a REPL. A tool with designed verbs, because a designed surface reads as a product and a REPL
reads as a script. The verb is the name: you *plumb* a claim.

```
plumb ask "where did we lose the ball most in the second half?"   # the answer, with its evidence
plumb ask --json "..."                                           # the same, machine-readable
plumb coverage --window second-half                              # what the tracking can and cannot carry
plumb why "..."                                                 # why the answer holds, or why it cannot
plumb close-gap "..."                                           # what would have to be collected to answer it
plumb ledger                                                    # metric | coverage | supported or refused | evidence frames
```

Output rules for the stage, because this is the part that gets rehearsed:

- **One question per screen**, cleared between beats. No scrollback.
- **Colour separates evidence from uncertainty**: the frames a claim rests on in one colour, the
  coverage and the confidence band in another. A jury reads colour in half a second.
- **The claim, then the grounds, then the provenance.** In that order.
- Never let a language model write a claim. The renderer is a prose layer over a structured
  evidence packet, so a hallucination is architecturally impossible and a refusal is exact.

## The five minutes

| Time | Beat |
|---|---|
| **0:00–0:40** | A question, answered live, with the evidence packet: frames counted, coverage, confidence band, the frames it rests on. Fast, confident, no preamble. |
| **0:40–2:30** | **The refusal.** A question the other finalists would answer confidently and wrongly — per-player attribution (there are no identities), or the shape of the second half's possession (that needs the private, corrected ground truth). The system declines, names the exact missing fields and where they would come from, and offers the nearest answerable proxy with its own weaker coverage. |
| **2:30–3:30** | Coverage as the *proof behind* the refusal, not as the opening slide: the 41 %, the two stoppages, the warm-up, the identity problem. The broken feed is now the reason the tool exists. |
| **3:30–4:20** | **Close-gap:** what would have to be collected for the refused question to become answerable. A refusal with a remedy is a roadmap, not a wall. |
| **4:20–5:00** | **Determinism.** Re-run the identical query with the network off and show byte-identical output. The last thing on screen is proof that the number and the refusal came from one reproducible artefact. |

Say the constraint out loud, once, in the first beat: *this data never leaves the laptop; the
reasoning is deterministic; every answer ships its sources.* It is the credibility beat and it
costs four seconds.

## The fallback

A recorded terminal session, committed to the repository, generated **by the committed code path**
against a pinned dataset snapshot with a checksum, plus the seed queries as a script. Play it
with `asciinema play` in the same terminal so the fallback is visually continuous with the live
run.

It is the insurance, the post-event audit trail, and the answer to "your data is broken": *here,
replay it.* It is never presented as the demo.

## What exists, and what has to exist before 2 March

**Built now (Phase 1 build, the shell of the demo):**
- [x] The CLI surface: `ask`, `why`, `close-gap`, `coverage`, `ledger`.
- [x] A fact library of seven deterministic claims, each with its coverage and its evidence.
- [x] Five refusal rules that name the missing evidence and the remedy.
- [x] The coverage interval: for a proportion, the worst case if every unobserved frame belonged
      to the other side. It is a hole in the claim, measured rather than assumed.
- [x] The ledger: one row per claim, with the feed's coverage and the claim's status.

**Still to build (the Innovation Challenge window, 26 Nov – 14 Jan):**
- [ ] The claim-scoped coverage model, validated on the ten-match dataset. The current coverage is
      per window; the refusal must be per claim.
- [ ] The fact library extended beyond possession to restarts, pressing, build-up, defending,
      transitions and chance creation.
- [ ] A refusal whose remedy is a *collection plan* — "three of eight matches lack that zone" —
      rather than a description of what is missing.
- [ ] The recorded session, generated from the committed path against a pinned snapshot.
- [ ] Four slides: the problem, the coverage, the refusal, the ledger.
- [ ] A rehearsal on a machine that is not the presenter's, with the fallback loaded and ready.
