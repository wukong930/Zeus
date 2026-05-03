from typing import Any


def classify_alert(signal: dict[str, Any], score: dict[str, Any] | Any | None = None) -> str:
    if signal.get("spread_info") is not None:
        return "L3"

    related_assets = [str(asset) for asset in signal.get("related_assets", [])]
    severity = str(signal.get("severity", "low"))
    priority = score_value(score, "priority")
    combined = score_value(score, "combined")

    if priority >= 85 or combined >= 85:
        return "L3"
    if severity in {"critical", "high"} or len(related_assets) >= 2:
        return "L2"
    if related_assets:
        return "L1"
    return "L0"


def score_value(score: dict[str, Any] | Any | None, key: str) -> float:
    if score is None:
        return 0.0
    if isinstance(score, dict):
        return float(score.get(key) or 0)
    return float(getattr(score, key, 0) or 0)
