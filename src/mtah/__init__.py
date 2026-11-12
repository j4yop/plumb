"""More Than A Hack 2027 — frame-level ball possession.

The public surface is deliberately small:

    from mtah.match import load_match
    from mtah.evidence import build_evidence
    from mtah.decide import assign_owners, build_spells

or, in one command::

    python -m mtah.run --out artifacts/submission.csv
"""

__all__ = ["config", "match", "evidence", "decide", "emit", "report"]

__version__ = "0.1.0"
