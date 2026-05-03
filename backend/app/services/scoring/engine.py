from dataclasses import dataclass

from app.services.scoring.margin_efficiency import margin_efficiency_score
from app.services.scoring.portfolio_fit import PositionGroup, RecommendationLeg, portfolio_fit_score
from app.services.scoring.priority import priority_score
from app.services.signals.types import SpreadInfo


@dataclass(frozen=True)
class CombinedScore:
    priority: int
    portfolio_fit: int
    margin_efficiency: int
    combined: int


def combine_scores(priority: int, portfolio_fit: int, margin_efficiency: int) -> int:
    return round(priority * 0.4 + portfolio_fit * 0.3 + margin_efficiency * 0.3)


def apply_calibration_weight(score: CombinedScore, calibration_weight: float) -> CombinedScore:
    calibrated_priority = round(max(0.0, min(100.0, score.priority * calibration_weight)))
    return CombinedScore(
        priority=calibrated_priority,
        portfolio_fit=score.portfolio_fit,
        margin_efficiency=score.margin_efficiency,
        combined=combine_scores(calibrated_priority, score.portfolio_fit, score.margin_efficiency),
    )


def score_recommendation(
    *,
    spread_info: SpreadInfo | None,
    confidence: float,
    legs: list[RecommendationLeg],
    open_positions: list[PositionGroup],
    margin_required: float,
    account_net_value: float,
) -> CombinedScore:
    priority = priority_score(spread_info, confidence)
    fit = portfolio_fit_score(legs, open_positions)
    efficiency = margin_efficiency_score(margin_required, account_net_value)

    return CombinedScore(
        priority=priority,
        portfolio_fit=fit,
        margin_efficiency=efficiency,
        combined=combine_scores(priority, fit, efficiency),
    )
