"""Validate our possession attribution against the organisers' own Smart Tagging.

Why this exists
---------------
The public five minutes cannot tell us which version of the system is best on the full match —
the organisers say so explicitly, and the four shipped baselines demonstrate it: the variant
that wins on the public window loses on the full match. So we need a signal that covers the
whole match and does not come from the forbidden five minutes.

Smart Tagging provides one. For 284 instances the tagging contains a *paired* attacking and
defending code covering the **same interval** with **opposite teams**:

    PROGRESSION            <-> DEFENDING IN MIDDLE THIRD
    ATTACKING TRANSITION   <-> DEFENSIVE TRANSITION
    BUILD UP               <-> DEFENDING IN ATTACKING THIRD
    CREATING CHANCES       <-> DEFENDING IN DEFENSIVE THIRD

An attacking phase ("progression", "build up", "creating chances") is a phase in which the named
team has the ball. A defending phase is one in which the named team does *not*. That is organiser
-provided automatic data about team possession over time — a supervision signal that covers the
entire match, uses no ground truth, and is not the public five minutes.

The test
--------
For every attacking instance, what fraction of its frames do we label with the attacking team?
For every defending instance, what fraction do we label with the *other* team?

A system that attributes possession correctly should score high on both. A system that has the
sides swapped scores near zero on both — which is exactly the failure this test is built to
catch, because a side swap is invisible in a dashboard and fatal to a score.
"""

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np
import pandas as pd

SMART = "data/tactical/BAR-ATH_tactical_smart_tagging.xml"
OURS = "artifacts/submission.csv"
WINDOW = (11185, 18685)

ATTACKING = {
    "PROGRESSION",
    "BUILD UP",
    "CREATING CHANCES",
    "ATTACKING TRANSITION",
    "LONG BALL",
    "BALL IN FINAL THIRD",
    "BALL IN THE BOX",
    "PLAYERS IN THE BOX",
}
DEFENDING = {
    "DEFENDING IN MIDDLE THIRD",
    "DEFENDING IN ATTACKING THIRD",
    "DEFENDING IN DEFENSIVE THIRD",
    "DEFENSIVE TRANSITION",
}
TEAM_TO_LABEL = {"Barcelona": "H", "Atletic Club": "A"}


def main():
    labels = pd.read_csv(OURS)["label"].values

    root = ET.parse(SMART).getroot()
    instances = []
    for instance in root.iter("instance"):
        code = instance.findtext("code")
        start = int(round(float(instance.findtext("start")) * 25))
        end = int(round(float(instance.findtext("end")) * 25))
        team = None
        for label in instance.findall("label"):
            if label.findtext("group") == "Team":
                team = (label.findtext("text") or "").strip()
        instances.append((code, start, end, team))

    print("our labels vs Smart Tagging team attribution (whole match)\n")
    buckets = defaultdict(list)
    for code, start, end, team in instances:
        if team not in TEAM_TO_LABEL:
            continue
        if not (code in ATTACKING or code in DEFENDING):
            continue
        # The whole match, not the public window: this is the point of the test.
        start = max(start, 0)
        end = min(end, len(labels))
        if end <= start:
            continue
        segment = labels[start:end]
        expected = TEAM_TO_LABEL[team]
        if code in DEFENDING:
            expected = "A" if expected == "H" else "H"
        # Agreement is measured only over the frames where we actually claim a team: a dead-ball
        # frame is not an attribution error, it is a different question.
        alive = segment[segment != "D"]
        if alive.size == 0:
            continue
        agreement = float(np.mean(alive == expected))
        buckets["all"].append(agreement)
        buckets[code].append(agreement)

    print("{:<34} {:>6} {:>10} {:>10}".format("code", "n", "agreement", "median"))
    for code in sorted(buckets):
        if code == "all":
            continue
        values = buckets[code]
        print("{:<34} {:>6} {:>9.1%} {:>10.1%}".format(
            code, len(values), float(np.mean(values)), float(np.median(values))))
    print("{:<34} {:>6} {:>9.1%} {:>10.1%}".format(
        "ALL", len(buckets["all"]), float(np.mean(buckets["all"])),
        float(np.median(buckets["all"]))))

    # How often do we disagree entirely (a side swap would show up as ~0%)?
    values = np.array(buckets["all"])
    print("\ninstances where we agree less than 25% of the time: {} of {}".format(
        int((values < 0.25).sum()), len(values)))
    print("instances where we agree more than 75% of the time: {} of {}".format(
        int((values > 0.75).sum()), len(values)))

    # A global side swap would show up here.
    print("\noverall H share of our alive frames: {:.3f}".format(
        float(np.mean(labels[labels != "D"] == "H"))))


if __name__ == "__main__":
    sys.exit(main())
