from app.services.signals.types import SpreadInfo


def priority_score(spread_info: SpreadInfo | None, confidence: float) -> int:
    score = 30.0

    if spread_info is not None:
        z_magnitude = abs(spread_info.z_score)
        score += min(30.0, z_magnitude * 10)

        half_life_bonus = max(0.0, (30 - spread_info.half_life) / 30) * 15
        score += half_life_bonus

        if spread_info.adf_p_value < 0.05:
            score += 10
        elif spread_info.adf_p_value < 0.1:
            score += 5

    score += max(0.0, min(1.0, confidence)) * 15
    return round(max(0.0, min(100.0, score)))
