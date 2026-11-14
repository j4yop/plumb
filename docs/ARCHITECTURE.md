# Architecture

The pipeline is eight stages. What follows is why each module has the shape it does, and where
the seams are.

```
        data/tactical/…
                │
                ▼
   ┌────────────────────────┐
   │  mtah.match            │   one interface: load_match(config) -> Match
   │  · metadata (teams,    │   everything behind it: XML parsing, the slot→team map,
   │    track slots)        │   streaming a 187 MB file, normalised → metres
   │  · tracking (players,  │   the frame-id ↔ video-frame contract
   │    ball)               │
   │  · Smart Tagging       │
   └────────────────────────┘
                │
                ▼
   ┌────────────────────────┐
   │  mtah.evidence         │   one interface: build_evidence(match, config) -> Evidence
   │  distances to the ball │   everything behind it: the distance matrix, the activity
   │  activity, phases,     │   statistics, the phase boundaries, the absence classes
   │  absence classes      │
   └────────────────────────┘
                │
                ▼
   ┌────────────────────────┐
   │  mtah.decide           │   two interfaces:
   │  control episodes      │     assign_owners(evidence, config) -> (owners, episodes)
   │  ownership             │     build_spells(owners, evidence, config) -> Decision
   │  spells, abstentions   │
   └────────────────────────┘
                │
                ▼
   ┌────────────────────────┐
   │  mtah.emit             │   write_submission(path, labels)
   │                        │   validate_file(path, n) -> problems
   │  mtah.report           │   summarise(labels, evidence, config) -> dict
   └────────────────────────┘
```

Above that pipeline sits the claims engine, which is the Phase-2 deliverable. It reads the
possession engine's output and never writes to it:

```
    Match ──▶ plumb.analysis ──▶ plumb.coverage      the reliability engine
                   │                plumb.tactics       the six tactical aspects
                   │                plumb.phases        the organisers' own annotation
                   ▼                     │
            plumb.facts  ────────────────┘
                   │                     scope, coverage, confidence, evidence
                   ▼
            plumb.router  ──▶  plumb.plan
                   │            the collection plan behind a refusal
                   ▼
            plumb.cli
```

## The seams, and why they are there

**The loading seam (`mtah.match`).** Everything that knows about file formats stops here. Callers
receive a `Match`: dense numpy arrays in metres, indexed by video frame, with the slot→team map
already resolved. Two things are deliberately *not* left to the caller:

- *The frame contract.* The ATD counts frames from 1 and a submission from 0. The reader asserts
  that the ids are contiguous and starts at 1, because a silent off-by-one shifts every possession
  by a frame and costs a fraction of a point that nothing would reveal.
- *Team order.* The first team in the metadata is the home team. Reading it from the metadata
  rather than hard-coding "the first 24 slots are home" means a change in the export cannot invert
  the sides silently — a side swap is invisible in a dashboard and fatal to a score.

**The evidence seam (`mtah.evidence`).** In the possession pipeline, coordinates never travel
past this module: everything downstream reads distances, counts and classifications. (The claims
engine is the exception, and deliberately so: a shape has to be measured from positions, so
`plumb.tactics` reads `player_xy` directly. It never writes back.) What comes out
is quantities a football person can reason about: metres to the ball for each team, how many
players are running, which phase the frame is in, and why the ball is missing.

The expensive part is one broadcast of the distance matrix — `n_frames × n_slots` float32, about
37 MB for the tactical recording — which is the price of vectorising the geometry. The whole
pipeline runs in under three seconds.

**The decision seam (`mtah.decide`).** This is where the football lives, and it is the module that
changed most while it was being written. What it knows:

- *Control.* A team controls the ball when the ball is within the control radius of one of its
  players and outside the other team's, and the team that is nearer is nearer by at least the
  hand-over margin. Both teams inside the radius means the ball is contested: nobody controls it.
- *Episodes.* Ownership is decided on maximal runs of control, not frame by frame. Short episodes
  are absorbed into their neighbours: a change of possession has to persist, and a pass that
  travelled within a metre of a defender is not a change of possession.
- *Dead ball.* A frame is dead when the ball is untracked and almost nobody is running, when the
  ball was last seen outside the pitch, or when it falls in the published warm-up block. It is
  deliberately conservative — see the technical document for the measurement that shaped it.
- *Abstention.* `X` is used sparingly and never next to a hand-over, because the scorer
  forward-fills an abstention with the previous label in the same half: abstaining inside a
  possession is free, abstaining across a hand-over carries the old label into the new state.

**The output seam (`mtah.emit`).** Writing the file is boring on purpose. The official checks are
re-implemented exactly, so a file that passes here cannot be rejected by the scorer, and the file
is written atomically — an interrupted run cannot leave a truncated submission that looks
complete.

## What is deliberately not in the pipeline

- **The video.** It is the source of the tracking, but at 1920×1080 with players twenty pixels
  tall it tells us nothing the tracking does not already say, and the broadcast video is not
  frame-aligned to the submission's timeline.
- **The homography.** It is 100 % valid on the tactical recording, and it is what turns the
  provider's normalised coordinates into metres. It is not needed to decide who has the ball, so
  it is not in the decision path — and it is not used to check the output against the video, which
  the rules forbid.
- **Any model.** There is no permitted training signal for this match: the labels we are scored on
  are private, and hand labels on the provided match are forbidden for training and validation
  alike. A rule-based system is therefore not a stylistic choice, it is the only honest one.
- **Any cloud service.** The competition's data must not be uploaded to a hosted model, and the
  pipeline does not need one.

## The failed experiments

They are in the code, switched off, with the reason recorded — a negative result is worth more
than a deleted branch.

| Experiment | Where | Why it failed |
|---|---|---|
| Repairing the slot→team map by spatial-neighbour voting | `mtah/teams.py`, `neighbour_team_voting` | The two teams interleave spatially, so neighbour voting recovers a left/right partition of the pitch rather than two teams, and it flips at half time when the teams change ends. It changed 13 % of slot-frames and inverted our possession share. |
| Inferring a hand-over during an occlusion from players converging on the ball's last known position | `mtah/decide.py`, `convergence_handover` | The last known position is a poor proxy once a long pass is in flight: the signal flipped in only two thirds of the true hand-overs we checked, and it cost accuracy. |
| Detecting dead ball from the ball being unattended | `scripts/deadball_rules.py` | 40–55 % precision. A false dead-ball period splits a real possession, so the conservative rule wins. |
| Letting the ball's displacement stand in for "is it in play" | `scripts/analyze_window.py` | A dead ball still moves (the keeper puts it down); the separation was weak. |
