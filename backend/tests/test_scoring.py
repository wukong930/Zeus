from app.services.scoring.engine import combine_scores, score_recommendation
from app.services.scoring.margin_efficiency import margin_efficiency_score
from app.services.scoring.portfolio_fit import (
    PositionGroup,
    RecommendationLeg,
    portfolio_fit_score,
)
from app.services.scoring.priority import priority_score
from app.services.signals.types import SpreadInfo


def test_priority_score_uses_z_score_half_life_and_stationarity() -> None:
    spread = SpreadInfo(
        leg1="RB",
        leg2="HC",
        current_spread=16,
        historical_mean=10,
        sigma1_upper=12,
        sigma1_lower=8,
        z_score=3,
        half_life=10,
        adf_p_value=0.03,
    )

    assert priority_score(spread, 0.8) == 92


def test_portfolio_fit_penalizes_overlap() -> None:
    legs = [RecommendationLeg(asset="RB", direction="long")]
    positions = [PositionGroup(legs=[RecommendationLeg(asset="RB", direction="short")])]

    assert portfolio_fit_score(legs, positions) == 55


def test_margin_efficiency_scores_capital_usage() -> None:
    assert margin_efficiency_score(10_000, 100_000) == 80
    assert margin_efficiency_score(0, 0) == 50


def test_combined_score_uses_phase1_static_weights() -> None:
    assert combine_scores(80, 70, 90) == 80


def test_score_recommendation_returns_all_dimensions() -> None:
    score = score_recommendation(
        spread_info=None,
        confidence=0.7,
        legs=[RecommendationLeg(asset="RB", direction="long")],
        open_positions=[],
        margin_required=10_000,
        account_net_value=100_000,
    )

    assert score.priority == 40
    assert score.portfolio_fit == 75
    assert score.margin_efficiency == 80
    assert score.combined == 62
