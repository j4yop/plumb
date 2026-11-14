"""One way to run the pipeline.

Why this module exists
----------------------
The three stages — evidence, ownership, spells — were pasted into seven call sites: the command
line, the claims engine, the audit, the ledger, and three diagnostic scripts. Each copy was
correct when it was written and each is a place for the next change to be forgotten.

That is the specific failure this project is about. A tool whose pitch is "the number is
reproducible" cannot have seven slightly different versions of the number.

So there is one function. Every caller gets the same three objects in the same order, and a change
to the decision stage reaches all of them at once.
"""

from __future__ import annotations

from typing import Optional, Tuple

from .config import Config
from .decide import Decision, assign_owners, build_spells
from .evidence import Evidence, build_evidence
from .match import Match, load_match


def evidence_for(match: Match, config: Config, teams=None) -> Evidence:
    """The evidence stage, on its own, for a caller that wants to report between the stages."""
    return build_evidence(match, config, teams=teams)


def decision_from(evidence: Evidence, config: Config) -> Decision:
    """The decision stage, on its own: ownership, then spells."""
    owners, episodes = assign_owners(evidence, config)
    return build_spells(owners, evidence, config, episodes=episodes)


def decide(match: Match, config: Config, teams=None) -> Tuple[Evidence, Decision]:
    """Evidence and decision for a match that is already loaded.

    This is the seam the diagnostic scripts need: they build a ``Match`` from a foreign format and
    then want the same decision the pipeline would have made.

    ``teams`` is the optional per-frame team membership from :mod:`mtah.teams`. It is off by
    default and measured as harmful (ADR 0005); it is a parameter so the negative result stays
    reproducible.
    """
    evidence = evidence_for(match, config, teams=teams)
    return evidence, decision_from(evidence, config)


def run(config: Config) -> Tuple[Match, Evidence, Decision]:
    """Load a match and decide it — the whole pipeline in one call."""
    match = load_match(config)
    evidence, decision = decide(match, config)
    return match, evidence, decision
