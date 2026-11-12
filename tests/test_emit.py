"""Writing the submission and checking it the way the official scorer checks it.

A file that breaks the contract is not scored — it is *dropped* with a one-line reason.
So the writer is deliberately boring and the validator re-implements the official checks:
a header, exactly ``n`` rows, the frame column 0..n-1 in order, no blank cells and a label
from the four-letter alphabet.
"""

import numpy as np
import pytest

from mtah.config import ABSTAIN, AWAY, DEAD, HOME, LABEL_NAMES
from mtah.emit import (
    EXPECTED_HEADER,
    read_submission,
    validate_file,
    validate_labels,
    write_submission,
)

GOOD_LABELS = [HOME, HOME, AWAY, DEAD, ABSTAIN]


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return str(path)


# --------------------------------------------------------------------------------------------------
# write_submission
# --------------------------------------------------------------------------------------------------


def test_write_submission_writes_a_header_and_one_row_per_frame(tmp_path):
    path = tmp_path / "submission.csv"
    write_submission(str(path), GOOD_LABELS)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert EXPECTED_HEADER == ["frame", "label"]
    assert lines[0] == ",".join(EXPECTED_HEADER)
    assert lines[1:] == ["0,H", "1,H", "2,A", "3,D", "4,X"]
    assert len(lines) == 1 + len(GOOD_LABELS)


def test_write_submission_maps_the_label_codes_to_letters(tmp_path):
    path = tmp_path / "submission.csv"
    write_submission(str(path), [HOME, AWAY, DEAD, ABSTAIN])

    body = path.read_text(encoding="utf-8").splitlines()[1:]
    assert [row.split(",")[1] for row in body] == list(LABEL_NAMES)


def test_write_submission_numbers_the_frames_from_zero(tmp_path):
    path = tmp_path / "submission.csv"
    write_submission(str(path), [HOME] * 3)
    body = path.read_text(encoding="utf-8").splitlines()[1:]
    assert [row.split(",")[0] for row in body] == ["0", "1", "2"]


def test_write_submission_leaves_no_temporary_file_behind(tmp_path):
    """The writer renames a temporary file into place, so an interrupted run cannot leave
    a truncated submission that looks complete."""
    path = tmp_path / "submission.csv"
    write_submission(str(path), GOOD_LABELS)
    assert [entry.name for entry in tmp_path.iterdir()] == ["submission.csv"]


def test_write_submission_creates_the_directory(tmp_path):
    path = tmp_path / "nested" / "deeper" / "submission.csv"
    write_submission(str(path), GOOD_LABELS)
    assert path.is_file()


def test_read_submission_reads_the_labels_back(tmp_path):
    path = tmp_path / "submission.csv"
    write_submission(str(path), GOOD_LABELS)
    codes = read_submission(str(path))
    assert codes.tolist() == GOOD_LABELS


# --------------------------------------------------------------------------------------------------
# validate_file
# --------------------------------------------------------------------------------------------------


def test_validate_file_accepts_a_good_file(tmp_path):
    path = tmp_path / "submission.csv"
    write_submission(str(path), GOOD_LABELS)
    assert validate_file(str(path), len(GOOD_LABELS)) == []


def test_validate_file_rejects_a_wrong_row_count(tmp_path):
    path = _write(
        tmp_path / "submission.csv",
        "frame,label\n0,H\n1,H\n2,A\n",
    )
    problems = validate_file(path, 5)
    assert any("row count 3 != 5" in problem for problem in problems)


def test_validate_file_rejects_a_blank_label_cell(tmp_path):
    path = _write(
        tmp_path / "submission.csv",
        "frame,label\n0,H\n1,\n2,A\n3,D\n4,X\n",
    )
    problems = validate_file(path, 5)
    assert any("empty label" in problem for problem in problems)


def test_validate_file_rejects_a_label_outside_the_alphabet(tmp_path):
    path = _write(
        tmp_path / "submission.csv",
        "frame,label\n0,H\n1,H\n2,H\n3,Z\n4,X\n",
    )
    problems = validate_file(path, 5)
    assert any("labels outside" in problem for problem in problems)
    assert any("'Z'" in problem for problem in problems)


def test_validate_file_rejects_a_non_monotonic_frame_column(tmp_path):
    path = _write(
        tmp_path / "submission.csv",
        "frame,label\n0,H\n1,H\n3,H\n2,H\n4,X\n",
    )
    problems = validate_file(path, 5)
    assert any("'frame' column is not 0..4 in order" in problem for problem in problems)


def test_validate_file_rejects_a_wrong_header(tmp_path):
    path = _write(tmp_path / "submission.csv", "frame,label,extra\n0,H\n")
    problems = validate_file(path, 1)
    assert any("expected frame,label" in problem for problem in problems)


def test_validate_file_reports_a_missing_file(tmp_path):
    problems = validate_file(str(tmp_path / "nope.csv"), 1)
    assert problems and "does not exist" in problems[0]


def test_validate_file_accepts_lower_case_labels(tmp_path):
    """The official checker upper-cases before comparing."""
    path = _write(tmp_path / "submission.csv", "frame,label\n0,h\n1,a\n2,d\n3,x\n")
    assert validate_file(path, 4) == []


# --------------------------------------------------------------------------------------------------
# validate_labels
# --------------------------------------------------------------------------------------------------


def test_validate_labels_accepts_a_good_sequence():
    assert validate_labels([HOME, AWAY, DEAD, ABSTAIN], 4) == []
    assert validate_labels(np.array([HOME, AWAY], dtype=np.int8), 2) == []


def test_validate_labels_rejects_a_wrong_length():
    problems = validate_labels([HOME, AWAY], 4)
    assert problems == ["row count 2 != 4"]


def test_validate_labels_rejects_an_unknown_code():
    problems = validate_labels([HOME, AWAY, DEAD, 7], 4)
    assert len(problems) == 1
    assert "labels outside" in problems[0]
    assert "7" in problems[0]


def test_validate_labels_rejects_a_negative_code():
    problems = validate_labels([-1, AWAY], 2)
    assert problems and "labels outside" in problems[0]


def test_validate_labels_stops_at_a_wrong_length():
    """A wrong row count is reported on its own: the labels are not even looked at."""
    assert validate_labels([HOME, 99], 5) == ["row count 2 != 5"]


def test_the_validator_and_the_writer_agree(tmp_path):
    """Everything the writer produces must pass the validator."""
    labels = [HOME, AWAY, DEAD, ABSTAIN] * 3
    path = tmp_path / "submission.csv"
    write_submission(str(path), labels)
    assert validate_file(str(path), len(labels)) == []
    assert validate_labels(labels, len(labels)) == []
