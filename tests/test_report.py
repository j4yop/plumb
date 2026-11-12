"""What the submission says about itself.

The official scorer reports numbers on the *private* ground truth; what we are allowed to
optimise is what we can measure ourselves. :func:`mtah.report.summarise` is that
self-measurement, so it has to be right: a wrong count in the report is a wrong number in
the technical document.
"""

import warnings

import numpy as np
import pytest

from mtah.config import ABSTAIN, AWAY, DEAD, HOME
from mtah.report import summarise


def test_summarise_counts_the_labels(evidence_factory, config):
    labels = np.array([HOME, HOME, AWAY, AWAY, DEAD, ABSTAIN], dtype=np.int8)
    evidence = evidence_factory(6)

    summary = summarise(labels, evidence, config)

    assert summary["frames"] == 6
    assert summary["label_counts"] == {"H": 2, "A": 2, "D": 1, "X": 1}
    assert summary["label_counts_graded"] == {"H": 2, "A": 2, "D": 1, "X": 1}


def test_summarise_counts_the_possessions(evidence_factory, config):
    labels = np.array([HOME, HOME, AWAY, AWAY, DEAD, ABSTAIN], dtype=np.int8)
    evidence = evidence_factory(6)

    summary = summarise(labels, evidence, config)

    # The two runs of a living team, and nothing else: `D` and `X` are not possessions.
    assert summary["possessions"] == 2
    assert summary["dead_spells"] == 1
    assert summary["home_share_of_alive"] == 0.5


def test_summarise_reports_the_durations_in_seconds(evidence_factory, config):
    """25 frames are one second: the durations are seconds, not frames."""
    labels = np.array([HOME] * 50 + [AWAY] * 25, dtype=np.int8)
    evidence = evidence_factory(75)

    summary = summarise(labels, evidence, config)

    assert summary["possessions"] == 2
    assert summary["mean_possession_s"] == 1.5
    assert summary["median_possession_s"] == 1.5
    assert summary["max_possession_s"] == 2.0


def test_summarise_reports_the_dead_time(evidence_factory, config):
    labels = np.array([HOME] * 25 + [DEAD] * 50, dtype=np.int8)
    evidence = evidence_factory(75)

    summary = summarise(labels, evidence, config)

    assert summary["dead_spells"] == 1
    assert summary["dead_seconds"] == 2.0


def test_summarise_uses_the_spells_it_is_given(evidence_factory, config):
    """The decision stage knows the spells; the report does not recompute them."""
    labels = np.array([HOME] * 10 + [AWAY] * 10, dtype=np.int8)
    evidence = evidence_factory(20)
    spells = [(0, 20, HOME)]

    summary = summarise(labels, evidence, config, spells=spells)

    assert summary["possessions"] == 1
    assert summary["dead_spells"] == 0


def test_summarise_reports_the_graded_frames_separately(evidence_factory, config):
    labels = np.array([HOME, AWAY, DEAD, ABSTAIN], dtype=np.int8)
    graded = np.array([True, True, False, False])
    evidence = evidence_factory(4, graded=graded)

    summary = summarise(labels, evidence, config)

    assert summary["graded_frames"] == 2
    assert summary["label_counts_graded"] == {"H": 1, "A": 1, "D": 0, "X": 0}
    assert summary["label_share_graded"]["H"] == 50.0
    assert summary["label_share_graded"]["D"] == 0.0


def test_summarise_reports_the_coverage(evidence_factory, config):
    labels = np.array([HOME, HOME, AWAY, AWAY], dtype=np.int8)
    ball_present = np.array([True, True, True, False])
    evidence = evidence_factory(4, ball_present=ball_present)

    summary = summarise(labels, evidence, config)

    assert summary["coverage"]["ball_present_frames"] == 3
    assert summary["coverage"]["ball_present_pct"] == 75.0


def test_summarise_reports_the_absence_classes(evidence_factory, config):
    labels = np.array([HOME, HOME, DEAD, DEAD], dtype=np.int8)
    evidence = evidence_factory(4)

    summary = summarise(labels, evidence, config)

    assert set(summary["absence_classes"]) == {"observed", "out_of_play", "stoppage", "warmup", "occlusion"}
    assert summary["absence_classes"]["observed"] == 4


def test_summarise_reports_the_phases(evidence_factory, config):
    labels = np.array([HOME, HOME], dtype=np.int8)
    evidence = evidence_factory(2)

    summary = summarise(labels, evidence, config)

    assert "first_half" in summary["by_phase"]
    assert summary["by_phase"]["first_half"]["frames"] == 2


def test_summarise_does_not_crash_on_an_empty_array(evidence_factory, config):
    labels = np.array([], dtype=np.int8)
    evidence = evidence_factory(0)

    with warnings.catch_warnings():
        # numpy warns about the mean of an empty slice; there is nothing to average.
        warnings.simplefilter("ignore")
        summary = summarise(labels, evidence, config)

    assert summary["frames"] == 0
    assert summary["label_counts"] == {"H": 0, "A": 0, "D": 0, "X": 0}
    assert summary["label_counts_graded"] == {"H": 0, "A": 0, "D": 0, "X": 0}
    assert summary["possessions"] == 0
    assert summary["dead_spells"] == 0
    assert summary["mean_possession_s"] == 0.0
    assert summary["max_possession_s"] == 0.0
    assert summary["home_share_of_alive"] == 0.0
    assert summary["graded_frames"] == 0
    assert summary["by_phase"] == {}


def test_summarise_does_not_crash_when_nobody_is_alive(evidence_factory, config):
    """A run with no possession at all: the shares must not divide by zero."""
    labels = np.array([DEAD, DEAD, ABSTAIN], dtype=np.int8)
    evidence = evidence_factory(3)

    summary = summarise(labels, evidence, config)

    assert summary["possessions"] == 0
    assert summary["home_share_of_alive"] == 0.0
    assert summary["label_share_graded"]["H"] == 0.0
