"""Write the submission, and check it against the official rules.

The file contract is unforgiving: exactly 199,319 rows, frames 0…199,318 in order, one of four
labels, no blank cells. A file that breaks it is not scored — it is *dropped* with a one-line
reason — which is the most expensive kind of mistake available: you would never know.

So the writer is deliberately boring and the validator re-implements exactly the checks the
official scorer runs.
"""

from __future__ import annotations

import os
import tempfile
from typing import Iterable, List, Sequence

import numpy as np

from .config import LABEL_NAMES

EXPECTED_HEADER = ["frame", "label"]


def write_submission(path: str, labels: Sequence[int]) -> str:
    """Write ``frame,label`` for every frame, atomically.

    The file is written to a temporary name in the same directory and renamed into place, so an
    interrupted run cannot leave a truncated submission that looks complete.
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        "w", dir=directory, prefix=".submission-", suffix=".csv", delete=False, newline="\n"
    )
    try:
        handle.write("frame,label\n")
        for frame, label in enumerate(labels):
            handle.write("{},{}\n".format(frame, LABEL_NAMES[int(label)]))
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        os.replace(handle.name, path)
    except BaseException:
        handle.close()
        if os.path.exists(handle.name):
            os.unlink(handle.name)
        raise
    return path


def validate_labels(labels: Sequence[int], n_expected: int) -> List[str]:
    """Check an in-memory label sequence. Returns a list of problems (empty means valid)."""
    problems: List[str] = []
    if len(labels) != n_expected:
        problems.append("row count {} != {}".format(len(labels), n_expected))
        return problems

    array = np.asarray(labels)
    unknown = sorted(set(int(v) for v in np.unique(array)) - set(range(len(LABEL_NAMES))))
    if unknown:
        problems.append("labels outside {}: {}".format(list(LABEL_NAMES), unknown[:5]))
    return problems


def validate_file(path: str, n_expected: int) -> List[str]:
    """Check a submission file exactly as the official scorer would.

    The official checks are: the header is ``frame,label``; there are exactly ``n_expected`` data
    rows; the ``frame`` column is the integers 0…n_expected-1 in order; no cell is blank; every
    label is one of H/A/D/X after stripping and upper-casing.
    """
    problems: List[str] = []
    if not os.path.isfile(path):
        return ["file does not exist: {}".format(path)]

    with open(path, "r", newline="") as handle:
        header = handle.readline().strip().split(",")
        if [h.strip().lower() for h in header] != EXPECTED_HEADER:
            problems.append(
                "header is {} , expected {}".format(header, ",".join(EXPECTED_HEADER))
            )
            return problems

        frames: List[int] = []
        labels: List[str] = []
        blanks = 0
        bad: List[str] = []
        for line in handle:
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = line.split(",")
            if len(parts) != 2:
                bad.append("row with {} fields: {!r}".format(len(parts), line[:40]))
                break
            frame_text, label_text = parts
            if frame_text.strip() == "" or label_text.strip() == "":
                blanks += 1
                continue
            frames.append(int(frame_text))
            labels.append(label_text.strip().upper())

    if bad:
        problems.extend(bad[:3])
    if len(frames) != n_expected:
        problems.append("row count {} != {}".format(len(frames), n_expected))
    if blanks:
        problems.append("empty label in {} rows; write X to abstain".format(blanks))
    if frames and frames != list(range(n_expected)):
        problems.append("'frame' column is not 0..{} in order".format(n_expected - 1))
    invalid = sorted(set(labels) - set(LABEL_NAMES))
    if invalid:
        problems.append("labels outside {}: {}".format(list(LABEL_NAMES), invalid[:5]))
    return problems


def read_submission(path: str) -> np.ndarray:
    """Read a submission file back into label codes (used by the scorer and by tests)."""
    out = []
    with open(path, "r", newline="") as handle:
        handle.readline()
        for line in handle:
            line = line.strip()
            if not line:
                continue
            label = line.split(",")[1].strip().upper()
            out.append(LABEL_NAMES.index(label))
    return np.asarray(out, dtype=np.int8)
