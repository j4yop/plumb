# Council Transcript — Which project topic for More Than A Hack 2027?

- **Conducted:** 12 Nov 2026, 21:04 IST
- **Question:** Which project topic from the *Premier League Project Ideas* list (PDF, @ethandojo) should this team build for More Than A Hack 2027, given the real competition structure and the audited data — so it is (a) compatible with the competition data, (b) real and not a gimmick, (c) demonstrably live and working to a jury, (d) most likely to win the Final pitch and its prizes.
- **Panel:** 5 independent advisors (parallel, same dossier) → 3 anonymous peer reviewers → Chairman synthesis.
- **Deadline context:** Phase 1 closes 17 Nov 2026 23:59 CET = **18 Nov 04:29 IST**. At time of deliberation, **5 days 7 hours remained**.

---

## Phase 1 — Deep Research Dossier

### Verified competition structure
Source: Metrica Sports official blog ("More Than A Hack 2027: build something real with FC Barcelona match data") + `github.com/metrica-sports/more-than-a-hack-2027`.

| Stage | Window | What it is |
|---|---|---|
| Registration | 1 Oct – 10 Nov 2026 | online |
| **Initial Challenge (Phase 1)** | 20 Oct – **17 Nov 2026** | label every frame of one match with team possession. **Ranked automatically, no jury.** Top 20 of 4,000+ entrants advance |
| **Innovation Challenge (Phase 2)** | **26 Nov 2026 – 14 Jan 2027** | top 20 teams get **10 professional matches with tracking AND event data**, and **open design challenges** instead of a scored task |
| **Final pitch** | **2 March 2027** | on site at Talent Arena, Barcelona. **5 teams, professional jury** |

Prizes: travel + accommodation to Barcelona, official FC Barcelona 26/27 shirts, Barça Innovation Hub merchandise, exclusive FC Barcelona experience. Teams of 3–5 (fewer than 3 ineligible for later stages).

### Phase 1 mechanics (from the repo)
- 199,319 frames (25 fps, 2 h 13 m). Labels `H` / `A` / `D` / `X`.
- Ranked on **`spellF1`**: possessions as intervals, one-to-one temporal-IoU matching, mean F1 over IoU 0.3–0.7. `macroF1` is the first tie-break.
- Published floor to beat: **spellF1 0.2433** (`baseline_smooth50`).
- `X` is **forward-filled with the last non-`X` label in the same half** (back-filled at half head) before spell matching. So `X` inside a possession is nearly free; `X` across a hand-over carries the old label across.
- **The public 5-minute ground truth is forbidden for training or tuning** — pipeline-correctness checking only.
- Deliverables: possession CSV (199,319 rows) + public repo that regenerates it **byte-for-byte** + short technical document.
- Rules: labels must come from an algorithm; **no hand labels on the provided match for any purpose** (training *or* validation); hand labels on **other** matches allowed; external data about other games allowed; **competition data must not be uploaded to third-party cloud LLMs**; organisers may re-run the repo to confirm reproduction.

### Data audit — measured directly from the official Drive bundle
- Tactical ATD: **199,319 records**, frame_id 1…199,319 contiguous, 46 groups/line, **46 track slots (24 Barcelona / 22 Athletic), no player identities**, normalised 0–1 coordinates, one record per video frame.
- Broadcast ATD: **164,488 records**, 51 slots. Broadcast video is **164,487 frames** — one-frame mismatch — and is **not** aligned to tactical.
- Tactical homography: 199,319 rows, **100% valid**, median reprojection error 0.239. Broadcast homography: 164,488 rows, **65.81% valid** (34% replays/close-ups/crowd shots).
- Smart Tagging (tactical only): **638 instances, 14 codes, 59 set pieces**. Team tags Barcelona 314 / Athletic 288 / **N/A 36 — including every throw-in**. Codes are **mirror pairs** (`PROGRESSION`↔`DEFENDING IN MIDDLE THIRD`, `ATTACKING TRANSITION`↔`DEFENSIVE TRANSITION`, `BUILD UP`↔`DEFENDING IN ATTACKING THIRD`, `CREATING CHANCES`↔`DEFENDING IN DEFENSIVE THIRD`) with identical intervals and opposite teams. **File order is grouped by code, not chronological.** Set-piece tags are 5 s (kick-offs) or 35 s windows, not exact restart frames.
- **Ball missing on 40.69 % of graded frames** (94,214 / 158,857 present). The two longest gaps — 138.6 s and 221.5 s — are both visible **stoppages**, not open-play loss.
- **Halftime: ball present 94.07 % of frames, ~12.5 players on pitch (warm-up).** A "ball visible = alive" rule mislabels halftime.
- **2,934 graded frames are `D`** before the second-half kickoff (frames 110,808–113,741).
- Track slots are very unevenly used (Track 44 never observed; Track 22 on 44 frames).
- Tactical video: fixed wide tactical camera, 199,319 frames, 1920×1080, with score/clock overlays. Broadcast: TV feed with cuts and replays.

### Idea list under consideration
1 Match Outcome Predictor · 2 Player Value Analyzer · 3 AI Scout · 4 Comeback Probability Calculator · 5 Expected Points Tracker · 6 Player Similarity Engine · 7 Formation Recognition Model · 8 Formation Change Detector · 9 Red Card Impact Model · 10 Substitution Impact Analyzer · 11 Home Advantage Calculator · 12 Automatic Highlight Generator · 13 Schedule Difficulty Calculator

### Hypothesis put to the council
Phase 1 is scored automatically, so a project idea cannot win Phase 1 — only the possession score can. The project is judged in March, and the Innovation Challenge is when it gets built. Hypothesis: **#8 Formation Change Detector (on a #7 Formation Recognition engine)** is the best pick — the only idea that genuinely requires the rare tracking data, identity-free, visually demonstrable, extending the Phase 1 engine.

---

## Phase 2 — Advisor Deliberations

### Advisor A — The Contrarian / Red Team
Verdict: hypothesis defensible but mis-ranked; its load-bearing claims each break on the audited data.

1. **Validation void (kill shot).** A formation detector has *no ground truth anywhere*. The bundle contains no formation labels, and the rules ban hand-labelling this match "for any purpose" — including validation. The 5-minute public truth that makes possession measurable is separately banned from tuning. So possession has a floor (0.2433) and a leaderboard; "formation change" has neither. The first jury question is "how do you know 4-2-3-1 became 4-3-3?" and the honest answer is "we thresholded a shape metric" — a heuristic demo, not a system.
2. **The dependency runs backwards.** Formation does not extend the possession engine; possession would feed *it*. Formation work buys **zero** Phase 1 score, and Phase 1 is the only thing that ranks you. Worse, the silent sink most teams underestimate: organisers re-run the repo byte-for-byte, so pin CPU, seeds and lockfiles — one GPU-nondeterminism bug can fail a correct solution on 17 Nov.
3. **Identity-free guts the demo.** 46 slots used erratically (Track 44 never observed; Track 22 on 44 frames), no IDs → you can compute *team shape* and nothing per-player. "Change detection" degenerates into thresholded noise on one wide-angle camera with rectilinear homography (depth error grows away from centre). Set pieces are 5 s/35 s windows, so the event timeline is ±seconds fuzzy before you even start.
4. **Ten matches is a demo reel, not a training set.** No list item can be an ML model. Pick a *system*, and prefer one whose load-bearing input only arrives on 26 Nov — event data with exact timestamps — which is precisely what fixes the fuzzy-window problem.
5. **Jury gimmick.** A formation chart is a commodity view; Metrica is a club-facing analytics vendor, so a formation pitch may read as re-implementing the sponsor's product. Prizes are travel, shirts and experience — reputational, not commercial.

**Recommendation:** #12 Automatic Highlight Generator (identity-free, tactical context). It shares ~all its code with the Phase 1 deliverable, demos honestly on one match, and its hard dependency — exact event timestamps — only lands in the innovation window, making the schedule coherent instead of padded. Keep formation as one panel inside it. Do not commit the project today — only possession commits now; the topic can be chosen on 26 Nov with the data in hand.

### Advisor B — The First Principles Thinker
Reframe the gate: Phase 1 is a **filter, not a prize** — automatic scoring, no jury, one binary outcome (top 20 of 4,000+). And the project *cannot* be built before 26 Nov — the 10-match tracking+event dataset doesn't exist until then. So pre-17-Nov idea work has no data behind it. **Spend 6 days ~85 % on the possession pipeline, 0 % on the idea.** The hypothesis's "extends Phase 1" logic is backwards for scheduling.

Attacking the hypothesis: the synergy claim is mostly false. Formation isn't a possession phenomenon — it needs the same ATD, not your spells. The one real bridge is Metrica's *own* labels: 638 tagged instances, 14 codes, paired mirrors with identical intervals and opposite teams — a provided, non-hand-made validation set for "does the shape index separate BUILD UP from PROGRESSION?" More valuable than a formation classifier.

Identity-free is a non-issue — 46 persistent track slots *are* pseudo-identities (Track 44 never observed). Good for feasibility; but it also proves the project doesn't need Phase 1's asset.

What breaks is **legitimacy, not feasibility.** Analysts will demand ground truth for "4-3-3" that doesn't exist. A hand-made taxonomy is the gimmick. Fix: continuous descriptors (width, line height, compactness, centroid, stretch, PPDA proxy) + change-point detection; formation names only as an overlay; attribute each change to exogenous events (subs, cards, phase) so output is *detected and explained*.

Unimpressive: a formation confusion matrix; "unknown" on 4-1-4-1; LLM narration (also rule-barred through cloud).

Hard constraint: Phase 2 guarantees only tracking + events → the project must be a function of those alone. That kills Highlights (needs video), Comeback Probability (needs calibrated history), Sub/Red Card Impact (10 matches, n ≈ 5).

**Phase 1 recipe:** nearest-slot-to-ball for the team; sustained ball-absent runs → D (the 138.6 s / 221.5 s gaps are stoppages) but never D at halftime's 94 % ball-present warm-up; min spell ≈ 2 s; merge same-team gaps; **abstain to X when unsure** (free inside a spell, costly across hand-overs). Resolve slot→team provenance in hour one — it swings difficulty an order of magnitude. Budget a full day for byte-for-byte reproduction: pinned deps, one entry point, deterministic row order.

**Verdict:** commit to **#8, with #7 as readout**, reframed as live shape+possession intelligence. 17–26 Nov: build the label-free engine (pitch-space features, descriptors, change-points, visualiser) and a batch harness so 10 matches ingest in hours on 26 Nov. Validate only on organiser labels; never hand labels.

### Advisor C — The Expansionist / Strategist
**Verdict:** pick **#12 (Automatic Highlight Generator), rebuilt as an automatic tactical-moment engine** with possession spells as its backbone.

Formation breaks on identity and arithmetic: identity-free geometry gives *shape*, not *roles*. "Formation change" is a role-level event (the 8 advancing, the striker dropping); with 46 anonymous slots — Track 44 never observed, Track 22 seen on 44 frames — role assignment is unsolvable. The deliverable degenerates into a line-chart of 11 dots, a broadcast commodity. Worse, it is an n=1 claim: one match, one opponent. Nothing generalises until 26 Nov, so it must be rebuilt in January anyway — it does **not** compound with Phase 1, it competes for the same hours.

**The binding risk is Phase 1, and it is not what the list implies.** The ball is missing on 40.69 % of graded frames, so you never "detect" possession — you *infer* it from geometry (cluster the 46 slots into two persistent spatial clusters, recover the 24/22 side split, then nearest-player/cone containment) and carry calibrated uncertainty. **That estimator is the reusable IP, not the CSV.** Treat it as a library. Traps to hard-code: halftime (ball present 94.07 %, ~12.5 players), 2,934 graded D frames (110,808–113,741), every throw-in N/A, 34 % of broadcast frames non-play (use tactical only). Under one-to-one temporal-IoU matching, over-segmentation is punished twice — merge aggressively, never emit X near a handover (X forward-fills only within a half), bias boundaries a few frames early. Tune on hand-labels of *other* matches (legal); the public 5-minute truth is poisoned, and no cloud LLMs.

**Split:** 6 days → 90 % pipeline-as-library, 10 % nothing else. 26 Nov–14 Jan → the moment engine on 10 tracked+event matches. 14 Jan–2 Mar → polish.

**Why #12 wins:** the 638 Smart Tagging instances (14 codes, 59 set pieces, mirror-paired opposite teams) are free supervision for "what counts as a moment" — the asset nobody else will mine. Every clip traceable to a spell, every label auditable, organisers can re-run the repo. It is also the umbrella: substitutions, red-card aftermaths and comeback arcs ship as downstream add-ons.

Higher-order: you exit with a licensed-clean, paper-shaped corpus — a 199k-frame possession benchmark plus tactical-moment supervision — and Barça's obvious future partner. The jury calls gimmick what it always calls gimmick: a reel without provenance, a formation chart without generality, a probability model without calibration. Ship the ones with a baseline.

### Advisor D — The Outsider / Domain Skeptic
**Verdict:** the topic is defensible; the framing is wrong. A Formation Change Detector is not a project layered *on top of* a possession pipeline — it **is** the pipeline's first stage. So 100 % of the next 6 days goes to the possession engine, and the March artifact starts 26 Nov.

What breaks in the hypothesis: the provided match cannot validate a formation detector — hand labels on that match are forbidden, so your only full-match supervision is Smart Tagging's 638 instances with 5 s/35 s windows, and you have **no substitution events until 26 Nov**. Without events, a vacated slot plus an arriving substitute is indistinguishable from a tactical reshuffle — that is the detector's core false-positive source, and a coach will kill the demo on it. Also: 24 slots for a side with an 18-man matchday squad, Track 44 never observed, ~12.5 warm-up players at halftime — you must infer the on-pitch set before you can count lines. And the ball is missing on 40.69 % of graded frames, so every ball-relative metric (line height vs. ball, compactness, press trigger) dies on two of every five frames. Only shape geometry survives, and shape is phase-conditional: "4-3-3" is a build-up shape or a defending shape, and phase labels come from those same 638 coarse codes.

What a Barça jury discounts: a formation heatmap on one match is what a club already produces from staff video — N=1, replication. "Comeback probability" and "expected points" are commodities; "schedule difficulty" would embarrass you. Identity-based ideas (Player Value, AI Scout, Similarity, Substitution Impact) are structurally dead — no identities in tactical ATD, and Phase 2 promises tracking + events, not identities.

**Where effort goes:** now → 17 Nov, pipeline only but built geometry-first — slot→team assignment, team-shape features, phase segmentation from the mirrored codes (`BUILD UP`↔`DEFENDING IN ATTACKING THIRD` etc.), then spells. One artefact serves both deadlines. Exploit the label asymmetry: `X` is forward-filled so abstaining inside a possession is nearly free, while a wrong `D` breaks the spell — emit `X` when the ball vanishes. 26 Nov → 14 Jan: the project on 10 matches, using the hand-label escape hatch (labels on any match *other than* the provided one are allowed) to gold-standard formations. That converts "n=1" into a measured claim.

### Advisor E — The Executor / Pragmatic Engineer
**Verdict:** keep #7 + #8, throw away the sequencing. The pick survives on execution grounds — but the plan for it is backwards.

Why the pick holds: it is the only listed idea that needs *nothing* but the ATD + homography. #4/#12 require reading the scoreboard overlay, which means local vision (competition data can't go to third-party cloud LLMs); #2/#3/#6/#9/#10 need identities and events the Phase-1 bundle lacks, and n=1 cannot support them; #13/#11/#5 are spreadsheets. And shape is **ball-independent** — the 40.7 % missing-ball rate that will wreck any event-detection idea doesn't touch formation at all.

**Where effort goes:** now–17 Nov (5 days): **100 % possession pipeline, zero formation code.** Three deliverables: CSV; byte-reproducible repo (lockfile, sorted iteration, fixed float format — organisers re-run it; budget a full day, most teams blow this); 2-page technical doc. One parallel background task only: pull 2–3 public tracking matches with known formations (Metrica sample data) as a validation set — legal, since hand labels are banned only on *this* match.

17–26 Nov gap: de-risk, don't build. Parse those external matches, hand-label formations (allowed elsewhere), build the line/role clusterer. Go/no-go on 26 Nov: if line assignment can't hit ~85 %, pivot. 26 Nov–14 Jan: build on the 10 pro matches; detect changes with minimum-dwell-time plus per-player displacement thresholds; ship a demo the jury can verify by watching video.

What breaks in the hypothesis: (1) "identity-free" covers teams, not roles — assigning 22 on-pitch slots to lines *is* the project, and it is what a Barça analyst attacks ("4-2-3-1 or 4-3-3? which midfielder is the pivot?"). Geometry alone cannot answer. (2) "Visually demonstrable live" cuts both ways: ~5 changes in one match means two false positives kills the demo. Forty events across 10 matches is the real demo, so build it in January, not now. (3) Exploit Smart Tagging — 638 paired-mirror intervals are coarse team-possession supervision, usable for sanity-checking both stages; get organiser sign-off in writing first.

**Rollback:** keep formation a module, not the spine. #12 remains the January fallback — it rides the event engine Phase 1 already builds.

---

## Phase 3 — Anonymous Peer Review

### Review 1 — Strongest Argument
**Response C is strongest.** Its core claim: with the ball missing on 40.69 % of graded frames, possession is never *detected* but *inferred* from slot geometry with calibrated uncertainty — and that estimator, not the CSV, is the reusable IP, so build a library, topic chosen 26 Nov. It alone ties audited facts to scoring math: under temporal-IoU 0.3–0.7, over-segmentation is punished twice (merge aggressively; never emit X near a handover); X forward-fills only within a half, so abstention inside a spell is nearly free; and it enumerates traps — halftime 94.07 % ball-present/~12.5 warm-up players, 2,934 D frames.

The rivals: A's "no formation ground truth" is true but only disqualifying — no mechanism, no winner. B's "Phase 1 is a filter" is right, yet its verdict (commit #8) contradicts it, and its 638-instance validation set ignores 5 s/35 s coarseness. D's substitute-vs-reshuffle ambiguity is the sharpest single attack on formation, but D never says what to build or how to score. E's ball-independent shape is real, but E's own findings (roles unresolvable, ~5 changes/match) sink its verdict; E lands on C's plan.

**Council: build the possession inference library by 17 Nov; ship #12 as a tactical-moment engine on the 638 Smart Tagging instances.**

### Review 2 — Fatal Blind Spot
**Response D.** Its rule *"emit X when the ball vanishes"* assumes `X` is a free, safe abstain class. Nothing in the audit defines `X`, its forward-fill behaviour, or how the grader scores it — and that one choice governs **40.69 % of graded frames**. If the truth there is H/A (spell continues through occlusion) or D, your X-predictions are false positives and H/A recall collapses; mean F1 lands at or below the 0.2433 floor and you are out of the top 20. Response B asserts the *opposite* rule ("sustained ball-absent runs → D") — the two contradict, which proves nobody has settled it. B's version is already arithmetically dead: 40.69 % missing ≈ 67 k frames vs only 2,934 graded D frames in H1, so ball-absent ≠ D.

**Cheapest retirement (½ day, before any modelling):** (1) ask organisers/Metrica for the D/X label schema; (2) align the 638 Smart Tagging windows to the ball-visibility timeline and read halftime (ball present 94.07 %, no play) as free probes; (3) submit two cheap probe CSVs (X-on-absent vs H/A-continued) and compare leaderboard F1.

### Review 3 — Missing Consideration
**Missing dimension: the grader's labelling contract — the hidden spec the Phase-1 score is actually computed against.** The metric is not "detect possession"; it is "reproduce the organisers' label function" (spell matching, temporal IoU 0.3–0.7). Those semantics live in the brief, not the data: what D vs X mean, which cluster is H and which is A, which frames are graded, how rows are indexed, whether resubmission is allowed. Five advisors each invented a confident policy — B: ball-absent→D; D: ball-vanishes→X; C: never emit X near a handover — and they contradict each other, so at least two are wrong. A swapped H/A or inverted D/X doesn't cost a few points; it collapses F1, you miss the top 20, and every project argument becomes moot. None budgeted one hour to certify the contract against the only authorities: the rules page, prior editions' repos, organiser confirmation.

**Same blind spot:** a public repo cannot ship the licensed ATD, so byte-for-byte regeneration needs a checksummed download path — unplanned by all five.

**Why it dominates:** Phase 1 is binary and gates everything after it. Project choice only pays if you pass.

**Council must decide:** (1) owner and deadline for certifying the contract; (2) a schema-correct baseline submitted ~14 Nov as insurance; (3) the project only afterwards, under the rule that it must survive merely mediocre possessions.

---

## Phase 4 — Chairman Synthesis

### 1. Where the Council Agrees (high confidence)
- **The next ~5 days are 100 % Phase 1.** All five advisors, unprompted, put essentially all pre-17-Nov effort into the possession pipeline. No advisor argued for building a project feature now.
- **The project topic must not be committed today.** Phase 2's 10-match tracking+event dataset does not exist until 26 Nov; the briefs are "open design challenges" and are not yet published.
- **Phase 1 is a gate, not a prize.** Binary outcome: top 20 of 4,000+. Project selection only pays if you pass it.
- **The reusable IP is the estimator, not the CSV.** The possession/control inference engine is the asset that survives into Phase 2 and that the Phase 1 repository and technical document are judged on.
- **Most of the PDF list is structurally incompatible.** 10 of 13 items need player identities (unavailable), many matches (10 is a demo reel, not a training set), market data, or calibrated historical samples that this competition does not provide. The judges are a Barça Innovation Hub / Metrica jury: they will discount generic football analytics instantly.

### 2. Where the Council Clashes (contested)
- **#8 Formation Change Detector vs #12 Highlight Generator.** A and C back #12 (reframed as a tactical-moment engine over the 638 Smart Tagging instances); B, D and E back #7/#8 with a continuous-descriptor, event-corroborated design.
  - *For #12:* its hard dependency (exact event timestamps) only arrives 26 Nov, so it cannot distract from Phase 1; it demos honestly on one match; Smart Tagging is free supervision for "what counts as a moment".
  - *Against #12:* **Metrica already supplies the event layer** — their own blog advertises "Automatic event data, generated with Smart Tagging. The events of the match, already tagged" — and they sell tactical tooling to clubs. Pitching "a highlight generator" at the sponsor's own event reads as re-implementing what the sponsor already hands you — and a jury's fastest word for that is *commodity*. It also needs a subjective "moment" definition, which is precisely where gimmicks live.
- **"Ball absent → D" vs "ball absent → X".** B says sustained absence means dead ball; D says emit X. The peer review showed B's version is arithmetically dead (≈67 k ball-absent frames vs only 2,934 graded D frames in H1), and D's version is an unverified bet on 40 % of the score. Both are wrong; the resolution is a *third* behaviour — infer deadness from evidence (absence + no player near the last known ball position + low player speed + set-piece tag + known half boundaries), and only then label D.
- **Ship a baseline early vs keep everything until the end.** Review 3 wants a schema-correct baseline submitted ~14 Nov as insurance. This is right, because SUBMISSION.md states one response per team, editable, **last response before the deadline is the one scored** — so an early submission is free optionality.

### 3. Blind Spots Caught in Peer Review
1. **The X-policy on ball-absent frames is the single highest-leverage unknown in the whole project** (40.69 % of graded frames). It needs certification, not guessing.
2. **Resubmission semantics must be confirmed before the strategy is fixed.** If only one submission counts, an early probe CSV could destroy the entry; if the last response counts, probing is free. SUBMISSION.md says the latter — verify it in writing.
3. **The public repo cannot contain the licensed ATD**, so "regenerates byte-for-byte" needs a documented, checksummed data-acquisition step (download + SHA-256 manifest), not a vendored dataset. None of the five advisors planned for this.
4. **A formation demo on one match is ~5 events; two false positives kills it.** The demo only becomes credible on 10 matches (≈40 events), which is another reason the project cannot be built before 26 Nov.
5. **Swap-in vs tactical reshuffle is unresolvable without event data** — a vacated slot plus an arriving substitute looks exactly like a reshuffle. The fix is to *require event corroboration* before declaring a change, which only Phase 2 makes possible.

### 4. The Recommendation (decisive)
- **Now → 18 Nov 04:29 IST: build the possession/control inference engine. Nothing else.** Deliverables in priority order: (1) CSV, (2) byte-reproducible repo, (3) technical document.
- **Project topic: #8 Formation Change Detector**, reframed and renamed so it is *not* a formation classifier:
  **"Event-corroborated shape-change & control intelligence"** — continuous shape descriptors + change-point detection, with formation names only as a read-out overlay, and every claimed change corroborated by Phase-2 event data. **#7 (Formation Recognition) is the engine; #12 (Automatic Highlight Generator) is the fallback if the 26 Nov briefs point at moments/highlights.**
- Rationale for the pick, in one line: it is the only listed idea that is *impossible without the rare tracking data* (the competition's entire premise), it survives the 41 % missing-ball problem because shape is ball-independent, it has a real evaluation story (continuous descriptors validated on other matches + organiser-provided Smart Tagging, never hand labels on this match), and its live demo is verifiable by a jury simply watching the video.

### 5. Concrete Action Plan (immediate next step, in order)
1. **Today (12 Nov):** email `hackathon.talentarena@mobileworldcapital.com` with three questions — (a) does `D` start at the infringement, the whistle, or the corrected tracking's dead flag (open issue #31, unanswered); (b) on a frame where the ball is not tracked during live play, is the truth `H`/`A` (spell continues) or `D`; (c) is the submission editable with the last response counted. Attach your proposed label semantics in one paragraph so they can approve or correct it.
2. **Today:** create the repo skeleton, pin numpy/pandas versions, lock seeds, and write the data-acquisition step as download + SHA-256 manifest (the licensed ATD must not be committed).
3. **13 Nov:** ship the slot→team provenance resolver and the ball/player feature extractor as a library, plus the nearest-player baseline — one command produces a 199,319-row CSV.
4. **14 Nov:** submit that baseline as **insurance** (editable submission, last response counts). Free optionality.
5. **14–16 Nov:** the two things that decide the score — (a) dead-vs-live inference (absence + proximity + player speed + set-piece tags + known half boundaries; halftime and the 2,934-frame block forced `D`); (b) temporal segmentation — one-to-one spell construction, min-duration, aggressive same-team merging, `X` only where genuinely uncertain and never near a hand-over.
6. **16 Nov:** byte-for-byte reproduction rehearsal from a clean clone, then final submission + technical document.
7. **17 Nov 20:00 IST:** submit. Deadline is 18 Nov 04:29 IST.

---

*Primary sources consulted:*
- `github.com/metrica-sports/more-than-a-hack-2027` — README, CHALLENGE.md, DATA.md, EVALUATION.md, SUBMISSION.md, RULES.md, FAQ.md, OVERVIEW.md, `evaluation/possession_metrics.py`, `evaluation/run_evaluation.py`, `evaluation/validate_submission.py`, `starter/*`, issues #2, #8, #10, #14, #15, #16, #17, #31 (open).
- `metrica-sports.com/blog/more-than-a-hack-2027-build-something-real-with-fc-barcelona-match-data` — six-month structure, prizes, eligibility.
- `landing.mobileworldcapital.com/more-than-a-hack-2027` — registration and stage overview.
- Official Drive bundle (`More Than A Hack 2027 - Initial Challenge - Dataset`) — all 8 non-video assets parsed in full; both videos inspected via container metadata and sampled frames.
- *Premier League Project Ideas*, @ethandojo (user-supplied PDF, 4 pages, 13 ideas).
- Formation literature for feasibility: npj *Complexity* "Shape graphs and the instantaneous inference of tactical positions in soccer"; arXiv EFPI (template matching + linear assignment for formation identification); Metrica sample-data tooling.
