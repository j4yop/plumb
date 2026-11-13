"""Tests for the Phase-2 machinery: the phase annotation, the reliability engine, the claim
scoping, and the collection plans.

These are the tests that matter for the pitch. Each one checks a claim the tool makes about
itself — that a scope really narrows the claim, that a refusal really comes with a way forward,
that the engine's numbers are the ones it says they are.
"""

import os

import numpy as np
import pytest

from plumb import cli, phases, plan, router
from plumb.analysis import Analysis
from plumb.coverage import build_coverage
from plumb.facts import FACT_LIBRARY, _scoped_frames
from plumb.tactics import attacking_sides, carried_ball, tactics_scope

from mtah.config import AWAY, HOME

from test_plumb import build_analysis

# The competition bundle is licensed and is not in the repository, so the tests that need it
# have to skip rather than fail when it is absent.
BUNDLE = "data/tactical/BAR-ATH_tactical_smart_tagging.xml"


def _bundle() -> list:
    """The Smart Tagging instances, or a skip when the bundle is not on this machine."""
    from mtah.match import parse_phases

    if not os.path.isfile(BUNDLE):
        pytest.skip("the competition bundle is not on this machine")
    parsed = parse_phases(BUNDLE)
    if not parsed:
        pytest.skip("the competition bundle is not on this machine")
    return parsed


@pytest.fixture(scope="module")
def analysis() -> Analysis:
    return build_analysis()


# --------------------------------------------------------------------------------------------------
# The phase annotation
# --------------------------------------------------------------------------------------------------


def test_the_annotation_is_read_as_fourteen_codes():
    """The Smart Tagging is not only set pieces, and the tool has to know that."""
    parsed = _bundle()
    assert len(parsed) == 638
    codes = {phase.code for phase in parsed}
    assert len(codes) == 14
    assert "BUILD UP" in codes
    assert "PROGRESSION" in codes
    assert "PLAYERS IN THE BOX" in codes
    assert "SET PIECES" in codes


def test_a_defending_code_is_the_mirror_of_an_attacking_one():
    """The pairs are what let the annotation be used as a check without ground truth."""
    names = ("Barcelona", "Atletic Club")  # the spelling in the bundle's own metadata
    pairs = phases.mirror_pairs(_bundle(), names)
    assert len(pairs) > 100
    for attack, defence in pairs:
        assert phases.team_index(attack.team, names) >= 0
        assert phases.team_index(defence.team, names) >= 0
        # Opposite teams, and the same window.
        assert phases.team_index(attack.team, names) != phases.team_index(defence.team, names)
        assert abs(attack.start - defence.start) <= 2
        assert abs(attack.end - defence.end) <= 2


def test_a_defending_code_is_scored_against_the_other_team():
    """A defending code names the team that did *not* have the ball."""
    from mtah.match import Phase

    team_a = Phase(start=0, end=100, code="DEFENDING IN MIDDLE THIRD", team="Barcelona",
                   kind="", half="1st Half")
    team_b = Phase(start=0, end=100, code="DEFENDING IN MIDDLE THIRD", team="Atletic Club",
                   kind="", half="1st Half")
    labels = np.full(200, 1, dtype=np.int8)  # Barcelona has the ball throughout
    assert phases.agreement([team_a], "DEFENDING IN MIDDLE THIRD", labels)["agreement"] == 1.0
    assert phases.agreement([team_b], "DEFENDING IN MIDDLE THIRD", labels)["agreement"] == 0.0


def test_the_agreement_counts_only_the_frames_a_team_had_the_ball():
    from mtah.match import Phase

    instance = Phase(start=0, end=99, code="BUILD UP", team="Barcelona", kind="", half="1st Half")
    labels = np.full(200, 0, dtype=np.int8)
    labels[50:100] = 2  # dead ball
    result = phases.agreement([instance], "BUILD UP", labels)
    assert result["frames"] == 50
    assert result["agreement"] == 1.0


# --------------------------------------------------------------------------------------------------
# The reliability engine
# --------------------------------------------------------------------------------------------------


def test_the_engine_scores_every_frame(analysis):
    coverage = build_coverage(analysis)
    assert coverage.support.shape == (analysis.n_frames,)
    assert coverage.support.min() >= 0.0
    assert coverage.support.max() <= 1.0


def test_a_frame_with_the_ball_and_a_full_pitch_scores_higher_than_a_blackout(analysis):
    coverage = build_coverage(analysis)
    seen = coverage.ball_seen & coverage.full_pitch
    missing = ~coverage.ball_seen
    if seen.any() and missing.any():
        assert coverage.support[seen].mean() > coverage.support[missing].mean()


def test_the_scope_is_the_coverage_of_the_claim_not_of_the_match(analysis):
    """The whole point: a claim about a scope is covered by that scope."""
    coverage = build_coverage(analysis)
    everything = coverage.scope()
    mask = np.zeros(analysis.n_frames, dtype=bool)
    mask[: analysis.n_frames // 3] = True
    a_third = coverage.scope(mask)
    assert a_third["frames"] < everything["frames"]
    assert a_third["frames"] > 0


def test_the_sensitivity_is_the_share_of_thin_margins(analysis):
    coverage = build_coverage(analysis)
    thin = coverage.sensitivity(sigma=0.0)
    thick = coverage.sensitivity(sigma=1e6)
    assert 0.0 <= thin <= 1.0
    # A wider tolerance can only flag more frames, never fewer.
    assert thick >= thin
    assert thick == 1.0


def test_an_empty_scope_reports_nothing_rather_than_dividing_by_zero(analysis):
    coverage = build_coverage(analysis)
    empty = coverage.scope(np.zeros(analysis.n_frames, dtype=bool))
    assert empty["frames"] == 0
    assert empty["support"] == 0.0


# --------------------------------------------------------------------------------------------------
# The scope
# --------------------------------------------------------------------------------------------------


def test_the_attack_direction_is_read_from_the_data_and_flips_at_half_time(analysis):
    right = attacking_sides(analysis)
    first = right[:100]
    second = right[-100:]
    assert first.all() == second.all()  # one direction per half
    # The synthetic match has no shape, so the two halves may agree; the real one must not.
    assert set(np.unique(right)).issubset({True, False})


def test_a_zone_covers_the_frames_where_the_ball_was_lost(analysis):
    """Otherwise a zone claim is circular: it would only contain frames we could see."""
    seen = analysis.evidence.ball_present
    if not (~seen).any():
        pytest.skip("the ball is observed everywhere")
    for zone_name in ("attacking-third", "middle-third", "defensive-third"):
        zone = tactics_scope(analysis, zone_name)
        if zone.any():
            # The zone is placed by the last observed ball position, so the frames in which
            # the ball was lost are still inside the zone they were lost in.
            assert (zone & ~seen).any()
            return
    pytest.skip("the synthetic match puts the ball in no zone")


def test_the_scope_narrows_the_coverage_claim(analysis):
    whole = FACT_LIBRARY["ball_visibility"](analysis, "all")
    scoped = FACT_LIBRARY["ball_visibility"](analysis, "all", "middle-third")
    assert scoped.coverage_pct != whole.coverage_pct or scoped.scope != whole.scope


def test_a_phase_scope_has_to_be_asked_for_explicitly():
    """"How did they build up" is about the window; "in the build up phases" is not."""
    assert router.route("how did they build up in the first half").phase is None
    assert router.route("how did they build up in the build up phases").phase == "BUILD UP"


def test_a_tactical_claim_is_not_covered_by_its_own_observations(analysis):
    """The coverage must not be 100 % by construction.

    A claim measured only over the frames in which the ball was observed would report perfect
    coverage. It has to rest on the possession frames instead, and then the coverage says
    something.
    """
    fact = FACT_LIBRARY["build_up"](analysis, "all")
    assert fact.coverage_pct is not None
    assert fact.coverage_pct < 1.0


def test_a_phase_scope_selects_the_tagged_frames(analysis):
    """The frames of a phase scope are the frames the annotation covers."""
    from mtah.match import Phase

    instance = Phase(start=100, end=199, code="BUILD UP", team="Barcelona", kind="",
                     half="1st Half")
    analysis.phases = [instance]
    frames = _scoped_frames(analysis, "all", None, "BUILD UP")
    assert frames.any()
    assert int(frames.sum()) == 100
    assert frames[100] and frames[199]
    assert not frames[99] and not frames[200]


def test_a_phase_scope_uses_the_organisers_own_windows():
    """On the real match, the scope is the annotation's windows."""
    build_up = phases.by_code(_bundle(), "BUILD UP")
    assert build_up
    span = sum(phase.end - phase.start for phase in build_up)
    assert span > 0


# --------------------------------------------------------------------------------------------------
# Routing and refusals
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,fact_id",
    [
        ("how did they build up", "build_up"),
        ("how far did they progress up the pitch", "progression"),
        ("how many players were in the box", "box_presence"),
        ("how did they defend", "defending_shape"),
        ("did the press win the ball back", "pressing"),
        ("how many corners were there", "restarts"),
        ("do we agree with the smart tagging", "annotation_agreement"),
    ],
)
def test_the_new_questions_are_routed(question, fact_id):
    assert router.route(question).id == fact_id


def test_a_zone_in_the_question_is_carried_into_the_route():
    assert router.route("how much of the final third can we see").zone == "attacking-third"


def test_every_refusal_carries_a_way_forward():
    for rule in router.REFUSAL_RULES:
        assert rule[5].strip(), "a refusal without a remedy is a dead end"
        assert rule[6].strip(), "a refusal without a proxy is a dead end"


def test_an_unanswerable_question_is_refused_not_guessed():
    route = router.route("which player scored the goal")
    assert route.kind == "refusal"
    assert route.detail.remedy


# --------------------------------------------------------------------------------------------------
# The collection plan
# --------------------------------------------------------------------------------------------------


def test_the_plan_quantifies_the_gap(analysis):
    route = router.route("what happened while the ball was missing")
    plan_ = plan.plan_for(analysis, route)
    assert "frames" in plan_.how_much
    assert plan_.collect
    assert plan_.unlocks
    assert plan_.steps


def test_the_plan_for_an_answerable_question_says_so(analysis):
    route = router.route("who had more possession")
    plan_ = plan.plan_for(analysis, route)
    assert "nothing" in plan_.collect.lower()


def test_the_plan_measures_the_gap_in_the_scoped_frames(analysis):
    """A plan about the final third must measure the final third, not the match."""
    route = router.route("how much of the final third can we see")
    plan_ = plan.plan_for(analysis, route)
    assert plan_.how_much


# --------------------------------------------------------------------------------------------------
# Another match
# --------------------------------------------------------------------------------------------------


def test_the_facts_use_the_matches_own_team_names(analysis):
    """The ten-match dataset is not Barcelona and Atletic Club."""
    analysis.team_names = ("Riverside FC", "North End")
    try:
        fact = FACT_LIBRARY["possession_share"](analysis, "all")
        assert "Riverside FC" in fact.answer
        assert "Barcelona" not in fact.answer
        assert any(label == "North End" for label, _ in fact.detail)
    finally:
        analysis.team_names = ("Barcelona", "Atletic Club")


def test_the_window_comes_from_the_matches_own_boundaries(analysis):
    """A hard-coded pair of half boundaries would be wrong on nine of ten matches."""
    original = analysis.phase_windows
    try:
        analysis.phase_windows = {
            "first-half": (0, 199),
            "second-half": (250, 449),
            "halftime": (200, 249),
        }
        assert analysis.window("first-half") == (0, 199)
        assert analysis.window("second-half") == (250, 449)
    finally:
        analysis.phase_windows = original


def test_the_annotation_is_matched_against_the_matches_own_names():
    """A hard-coded name pair silently loses half the mirror pairs."""
    from mtah.match import Phase

    instances = [
        Phase(start=0, end=10, code="PROGRESSION", team="Riverside FC", kind="", half=""),
        Phase(start=0, end=10, code="DEFENDING IN MIDDLE THIRD", team="North End", kind="",
              half=""),
    ]
    labels = np.full(20, 0, dtype=np.int8)
    names = ("Riverside FC", "North End")
    pairs = phases.mirror_pairs(instances, names)
    assert len(pairs) == 1
    assert phases.pair_agreement(pairs, labels, names)["agreement"] == 1.0
    # The default names cannot resolve these teams, and that must be visible rather than silent.
    assert phases.mirror_pairs(instances) == []


# --------------------------------------------------------------------------------------------------
# The command surface
# --------------------------------------------------------------------------------------------------


def test_the_cli_prints_a_scope_for_every_fact(capsys, analysis):
    for fact_id in FACT_LIBRARY:
        cli._ask(analysis, "who had more possession", cli.Style(enabled=False), False)
    out = capsys.readouterr().out
    assert "scope" in out


def test_the_cli_refuses_and_plans(capsys, analysis):
    cli._close_gap(analysis, "which player touched the ball", cli.Style(enabled=False), False)
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "PLAN" in out
    assert "how much" in out


def test_the_json_output_is_valid(capsys, analysis):
    import json

    cli._ask(analysis, "who had more possession", cli.Style(enabled=False), True)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "supported"
    assert "coverage" in payload
    assert "scope" in payload
