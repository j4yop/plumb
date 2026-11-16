# Short technical summary — for the submission form

If the form's "Short technical document" field is a **text box** rather than a file upload, paste
this. If it is an upload, use `artifacts/Chappal-technical-document.pdf` (11 pages, generated from
`docs/TECHNICAL.md`).

---

**Team Chappal — frame-level ball possession, More Than A Hack 2027**

**Approach.** A deterministic, CPU-only pipeline in numpy. For every frame it computes the distance
from the ball to every tracked player, assigns control when the ball is inside one team's control
radius (2.0 m) and outside the other's by at least the hand-over margin (0.5 m), and then decides
ownership in **episodes** rather than per frame: a control change must persist for 12 frames to
count, and a spell shorter than 25 frames is absorbed. Deciding per frame shattered one 41-second
truth possession into seven pieces; deciding in episodes brought the possession count from 24 to
18 against the organisers' 17 on the public window.

**Assets used and dropped.** The tactical ATD tracking is the whole decision path; the metadata
supplies team names and the slot→team map. The Smart Tagging is used as a validation reference
(638 instances, fourteen codes) and never as a label source. The homography is valid on 100 % of
frames but adds nothing to the decision. The **broadcast** recording is dropped: 65.81 % of its
homography is valid, it has cuts and replays, and its frame count differs from its tracking by one.

**Training data.** None. There is no permitted training signal for this match, and hand labels on
the provided game are forbidden for training or validation. The system has no model and no fitted
parameter; every threshold is a football quantity in metres or seconds.

**How the thresholds were chosen.** Not on the ground-truth possession labels and not on the video.
Three legal routes, all in the repository: an **external tuning set** of three public Metrica sample
matches with event-derived possession truth (`scripts/external_tuning.py`); a **label-free
perturbation-stability criterion** on the tracking — hide a fifth of the ball observations and ask
how many possessions still exist at the metric's own headline IoU, which gives the same knee at 25
frames on four independent matches (`scripts/stability_sweep.py`); and football statements for the
rest. The public five minutes are used only to check that the frames are aligned and to read what
the organisers' labels mean.

**Possession rules implemented.** Control not proximity; episodes not frames; dead ball as a play
state rather than a missing ball (the ball is *visible* in two thirds of the frames the organisers
call dead — what separates them is that the players are not running); `X` only where no owner is
defensible and never adjacent to a hand-over.

**Results.** `spellF1` 0.5000, `macroF1` 0.6878 on the public five-minute window, above all four
shipped baselines (best baseline 0.4242). 306 possessions over the match, mean 14.2 s. 3.1 s
runtime, one core. The file is byte-reproducible from the raw tracking.

**Validation without ground truth.** The Smart Tagging pairs an attacking code with a defending
code over the same interval with opposite teams for 140 windows, which states who had the ball. Our
labels agree with it on 70.3 % of the 72,560 frames those windows cover, counting an abstention as
wrong (77.6 % of the frames where we name a team). We also reproduce the organisers' own "max
players in the box" count exactly in 74 of 91 tagged instances, and within one player in 90.

**Limitations, stated.** Dead-ball recall is about 28 % by choice — a false dead period splits a
real possession, a missed one only makes one slightly long. Hand-overs are detected late because
the ball is untracked around 41 % of the time. There are no player identities: 46 anonymous slots
for 22 players, and the organisers warn that slots swap. Everything is one match.

**Reproduction.** `git clone https://github.com/j4yop/plumb`, `pip install -r requirements.txt`,
put the licensed bundle in `data/`, then `make reproduce` (3 s) and `make validate`. The data is not
in the repository; `MANIFEST.sha256` carries the checksums.
