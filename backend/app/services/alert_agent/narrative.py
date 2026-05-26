from typing import Any

from app.services.alert_agent.dedup import normalize_severity, normalize_symbol


def generate_narrative(signal: dict[str, Any], classification: str) -> str:
    summary = str(signal.get("summary") or "").strip()
    if summary:
        return summary
    title = str(signal.get("title") or "Signal triggered").strip()
    severity = normalize_severity(signal.get("severity"))
    return f"{title} classified as {classification} with {severity} severity."


def generate_one_liner(signal: dict[str, Any], classification: str) -> str:
    symbol = primary_symbol(signal)
    signal_type = str(signal.get("signal_type") or "signal")
    severity = normalize_severity(signal.get("severity"))
    text = f"{symbol} {severity} {signal_type} {classification}"
    return text[:30].rstrip()


def primary_symbol(signal: dict[str, Any]) -> str:
    related_assets = signal.get("related_assets") or []
    for asset in related_assets:
        symbol = normalize_symbol(asset)
        if symbol:
            return symbol
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict) and spread_info.get("leg1") is not None:
        symbol = normalize_symbol(spread_info["leg1"])
        if symbol:
            return symbol
    return "MARKET"
