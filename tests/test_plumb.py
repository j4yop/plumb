"""Tests for the plumb interface: the router, the refusals, and the command surface."""

import numpy as np
import pytest

from plumb import cli, router
from plumb.analysis import Analysis
from plumb.facts import FACT_LIBRARY, possession_share

from mtah.config import Config
from mtah.decide import assign_owners, build_spells
from mtah.evidence import build_evidence
from mtah.match import Match


# --------------------------------------------------------------------------------------------------
# A tiny synthetic match, built the same way the rest of the suite builds them
# --------------------------------------------------------------------------------------------------


def make_config() -> Config:
    """A configuration whose graded window starts at frame 0."""
    return Config(
        pre_match_frames=(-100, -1),
        first_half_frames=(0, 100_000),
        half_time_frames=(100_001, 200_000),
        second_half_frames=(200_001, 300_000),
        second_half_kickoff_frame=200_003,
        post_match_frames=(300_001, 400_000),
    )


def build_analysis(n_frames: int = 600, seed: int = 0) -> Analysis:
    """A synthetic analysis: two teams, a ball that is often unobserved."""
    rng = np.random.RandomState(seed)
    config = make_config()

    n_slots = 22
    slot_team = np.array([0] * 11 + [1] * 11, dtype=np.int8)
    player_xy = np.zeros((n_frames, n_slots, 2), dtype=np.float32)
    player_speed = np.zeros((n_frames, n_slots), dtype=np.float32)
    for index in range(n_slots):
        side = 0.0 if index < 11 else 80.0
        player_xy[:, index, 0] = side + rng.rand(n_frames) * 20.0
        player_xy[:, index, 1] = 5.0 + rng.rand(n_frames) * 58.0
        player_speed[:, index] = rng.rand(n_frames) * 4.0

    ball_xy = np.zeros((n_frames, 2), dtype=np.float32)
    # The ball sits at the feet of a home player for the first half of the frames and an away
    # player for the second, with a little noise — so there is real possession to find.
    carrier = np.where(np.arange(n_frames) < n_frames // 2, 0, 11)
    ball_xy[:, 0] = player_xy[np.arange(n_frames), carrier, 0] + rng.randn(n_frames) * 0.4
    ball_xy[:, 1] = player_xy[np.arange(n_frames), carrier, 1] + rng.randn(n_frames) * 0.4
    # The ball is unobserved on a quarter of the frames.
    ball_visible = rng.rand(n_frames) > 0.25
    ball_xy[~ball_visible] = np.nan

    match = Match(
        n_frames=n_frames,
        n_slots=n_slots,
        team_names=("Barcelona", "Atletic Club"),
        slot_team=slot_team,
        player_xy=player_xy,
        player_speed=player_speed,
        ball_xy=ball_xy,
        ball_speed=np.full(n_frames, np.nan, dtype=np.float32),
        set_pieces=(),
    )
    evidence = build_evidence(match, config)
    owners, episodes = assign_owners(evidence, config)
    decision = build_spells(owners, evidence, config, episodes=episodes)
    return Analysis(
        labels=decision.labels,
        spells=decision.spells,
        evidence=evidence,
        ball_xy=match.ball_xy,
        player_xy=match.player_xy,
        player_speed=match.player_speed,
        slot_team=match.slot_team,
        n_frames=n_frames,
    )


@pytest.fixture(scope="module")
def analysis() -> Analysis:
    return build_analysis()


# --------------------------------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,fact_id",
    [
        ("who had more possession in the first half?", "possession_share"),
        ("how many possessions were there", "possession_count"),
        ("how much of the match was dead ball", "dead_ball"),
        ("what was the longest possession", "longest_possession"),
        ("how much of this match can we actually see", "ball_visibility"),
        ("how often did possession change hands", "possession_changes"),
        ("where was the ball, by third", "ball_thirds"),
    ],
)
def test_questions_route_to_their_fact(question, fact_id):
    route = router.route(question)
    assert route.kind == "fact"
    assert route.id == fact_id


def test_a_window_is_read_out_of_the_question():
    assert router.route("possession share in the first half").window == "first-half"
    assert router.route("possession share in the second half").window == "second-half"
    assert router.route("possession share over the whole match").window == "all"
    assert router.route("possession share").window == "all"


# --------------------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,refusal_id",
    [
        ("which player touched the ball most", "player_identity"),
        ("how many shots did Barcelona have", "event_data"),
        ("what does the ground truth say", "ground_truth"),
        ("how does this compare with other matches", "other_matches"),
        ("what happened while the ball was missing", "missing_ball"),
    ],
)
def test_questions_the_data_cannot_answer_are_refused(question, refusal_id):
    route = router.route(question)
    assert route.kind == "refusal"
    assert route.id == refusal_id


def test_a_refusal_carries_a_way_forward():
    route = router.route("which player touched the ball most")
    refusal = route.detail
    assert refusal.why  # says why
    assert refusal.missing  # says what is missing
    assert refusal.remedy  # says what to collect
    assert refusal.proxy  # says what can be answered instead


def test_a_refusal_wins_over_a_fact():
    """A per-player question that also mentions possession must still be refused."""
    route = router.route("what was the possession share, and which player won it?")
    assert route.kind == "refusal"


def test_an_unrecognised_question_returns_no_route():
    route = router.route("what is the weather in Barcelona")
    assert route.kind == "unknown"


# --------------------------------------------------------------------------------------------------
# Facts
# --------------------------------------------------------------------------------------------------


def test_a_fact_carries_its_evidence(analysis):
    fact = possession_share(analysis, "all")
    assert fact.answer
    assert fact.coverage
    assert fact.confidence
    assert fact.evidence


def test_the_confidence_interval_brackets_the_value(analysis):
    """The interval must contain the value, and it must be wider than a point."""
    import re

    fact = possession_share(analysis, "all")
    matches = [(label, v) for label, v in fact.detail if label == "Barcelona"]
    assert matches, ("no Barcelona row in", fact.detail, fact.answer)
    home = float(matches[0][1].split()[0])
    low, high = [float(x) for x in re.findall(r"([0-9.]+) %", fact.confidence)[:2]]
    assert low - 0.5 <= home <= high + 0.5
    assert high > low  # the feed has holes, so the interval is not a point


def test_every_fact_in_the_library_answers(analysis):
    for name, function in FACT_LIBRARY.items():
        fact = function(analysis, "all")
        assert fact.answer, name
        assert fact.coverage, name


# --------------------------------------------------------------------------------------------------
# The command surface
# --------------------------------------------------------------------------------------------------


def test_the_cli_answers_a_question(capsys, monkeypatch, analysis):
    monkeypatch.setattr(cli, "analyse", lambda config, use_cache=True: analysis)
    code = cli.main(["--no-colour", "ask", "who had more possession"])
    assert code == 0
    out = capsys.readouterr().out
    assert "SUPPORTED" in out
    assert "Barcelona" in out


def test_the_cli_refuses_a_question_it_cannot_answer(capsys, monkeypatch, analysis):
    monkeypatch.setattr(cli, "analyse", lambda config, use_cache=True: analysis)
    code = cli.main(["--no-colour", "ask", "which player touched the ball most"])
    assert code == 0
    out = capsys.readouterr().out
    assert "REFUSED" in out
    assert "missing" in out
    assert "remedy" in out


def test_the_cli_emits_json(capsys, monkeypatch, analysis):
    import json

    monkeypatch.setattr(cli, "analyse", lambda config, use_cache=True: analysis)
    cli.main(["--no-colour", "--json", "ask", "how much of the match can we see"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "supported"
    assert payload["coverage"]


def test_the_cli_emits_json_for_a_refusal(capsys, monkeypatch, analysis):
    import json

    monkeypatch.setattr(cli, "analyse", lambda config, use_cache=True: analysis)
    cli.main(["--no-colour", "--json", "ask", "how many shots were there"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "refused"
    assert payload["remedy"]


def test_the_ledger_lists_every_fact(capsys, monkeypatch, analysis):
    monkeypatch.setattr(cli, "analyse", lambda config, use_cache=True: analysis)
    cli.main(["--no-colour", "ledger"])
    out = capsys.readouterr().out
    for name in FACT_LIBRARY:
        assert name in out
    assert "supported" in out
