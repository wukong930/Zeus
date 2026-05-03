from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationLeg:
    asset: str
    direction: str
    lots: float = 1


@dataclass(frozen=True)
class PositionGroup:
    legs: list[RecommendationLeg]


def portfolio_fit_score(legs: list[RecommendationLeg], open_positions: list[PositionGroup]) -> int:
    if not open_positions:
        return 75

    leg_assets = {leg.asset for leg in legs}
    conflict_penalty = 0.0
    diversification_bonus = 0.0

    for position in open_positions:
        position_assets = {leg.asset for leg in position.legs}
        if not position_assets:
            continue

        overlap = leg_assets.intersection(position_assets)
        if overlap:
            denominator = max(len(leg_assets), len(position_assets), 1)
            conflict_penalty += 20 * (len(overlap) / denominator)

        diversification_bonus += 5

    score = 70 - min(40, conflict_penalty) + min(20, diversification_bonus)
    return round(max(0.0, min(100.0, score)))
