"""Audit which track slots can be trusted to belong to a team.

The metadata assigns every track slot to a team, but the organisers warn that slots "appear,
vanish and swap identity as the tracker loses and re-acquires people". A slot that has swapped
carries the wrong team label from that moment on, and a slot that is often the nearest to the
ball is expensive to get wrong.

The test uses the organisers' own automatic event data. For 284 intervals the Smart Tagging
contains an attacking code and a defending code covering the *same* interval with *opposite*
teams, so for those intervals we know which team has the ball. For every frame in them, we look
at the slot nearest the ball and ask whether that slot's metadata team agrees with the team the
tagging says has the ball.

A slot that is nearly always right is trustworthy. A slot near 50% is switching identity.
"""

import sys
import xml.etree.ElementTree as ET
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, "src")
from mtah.match import parse_meta  # noqa: E402

ATD = "data/tactical/BAR-ATH_tactical_atd.txt"
SMART = "data/tactical/BAR-ATH_tactical_smart_tagging.xml"

ATTACKING = {
    "PROGRESSION", "BUILD UP", "CREATING CHANCES", "ATTACKING TRANSITION",
    "LONG BALL", "BALL IN FINAL THIRD", "BALL IN THE BOX", "PLAYERS IN THE BOX",
}
DEFENDING = {
    "DEFENDING IN MIDDLE THIRD", "DEFENDING IN ATTACKING THIRD",
    "DEFENDING IN DEFENSIVE THIRD", "DEFENSIVE TRANSITION",
}
TEAM_TO_INDEX = {"Barcelona": 0, "Atletic Club": 1}


def tagged_intervals():
    """(start, end, expected team index) for the attacking and defending phases."""
    root = ET.parse(SMART).getroot()
    intervals = []
    for instance in root.iter("instance"):
        code = instance.findtext("code")
        if code not in ATTACKING and code not in DEFENDING:
            continue
        team = None
        for label in instance.findall("label"):
            if label.findtext("group") == "Team":
                team = (label.findtext("text") or "").strip()
        if team not in TEAM_TO_INDEX:
            continue
        start = int(round(float(instance.findtext("start")) * 25))
        end = int(round(float(instance.findtext("end")) * 25))
        expected = TEAM_TO_INDEX[team]
        if code in DEFENDING:
            expected = 1 - expected
        intervals.append((start, end, expected))
    return intervals


def main():
    names, slot_team = parse_meta("data/tactical/BAR-ATH_tactical_atd.xml")
    print("teams:", names)

    intervals = tagged_intervals()
    wanted = {}
    for start, end, expected in intervals:
        for frame in range(start, end):
            wanted[frame] = expected
    print("{} tagged frames of team attribution available".format(len(wanted)))
    if not wanted:
        return

    agree = np.zeros(len(slot_team))
    total = np.zeros(len(slot_team))
    used = np.zeros(len(slot_team))

    with open(ATD) as handle:
        for line in handle:
            parts = line.strip().split(":")
            frame_id = int(parts[0])
            frame = frame_id - 1
            if frame not in wanted:
                continue
            groups = parts[1].split(";")
            ball = parts[2].split(",")
            if ball[0] == "N":
                continue
            bx = float(ball[0]) * 105.3
            by = float(ball[1]) * 68.0
            best_slot = -1
            best_distance = float("inf")
            for index, group in enumerate(groups):
                if group[0] == "N":
                    continue
                values = group.split(",")
                dx = float(values[0]) * 105.3 - bx
                dy = float(values[1]) * 68.0 - by
                distance = dx * dx + dy * dy
                if distance < best_distance:
                    best_distance = distance
                    best_slot = index
            if best_slot < 0 or best_distance > 2.25:
                continue
            total[best_slot] += 1
            used[best_slot] += 1
            if slot_team[best_slot] == wanted[frame]:
                agree[best_slot] += 1

    print("\nslot  times-nearest  agrees-with-tagging   verdict")
    suspect = []
    for slot in range(len(slot_team)):
        if total[slot] < 20:
            continue
        rate = agree[slot] / total[slot]
        verdict = ""
        if rate < 0.6:
            verdict = "<-- UNRELIABLE (switches identity?)"
            suspect.append(slot + 1)
        elif rate < 0.8:
            verdict = "<- mixed"
        print("  {:>3}  {:>13}  {:>18.1%}   {}".format(
            slot + 1, int(total[slot]), rate, verdict))

    print("\nunreliable slots: {}".format(suspect))
    print("slots never the nearest to the ball: {}".format(
        [s + 1 for s in range(len(slot_team)) if total[s] < 20]))


if __name__ == "__main__":
    sys.exit(main())
