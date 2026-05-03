from typing import Any


def generate_narrative(signal: dict[str, Any], classification: str) -> str:
    summary = str(signal.get("summary") or "").strip()
    if summary:
        return summary
    title = str(signal.get("title") or "Signal triggered").strip()
    severity = str(signal.get("severity") or "low")
    return f"{title} classified as {classification} with {severity} severity."


def generate_one_liner(signal: dict[str, Any], classification: str) -> str:
    symbol = primary_symbol(signal)
    signal_type = str(signal.get("signal_type") or "signal")
    severity = str(signal.get("severity") or "low")
    text = f"{symbol} {severity} {signal_type} {classification}"
    return text[:30].rstrip()


def primary_symbol(signal: dict[str, Any]) -> str:
    related_assets = signal.get("related_assets") or []
    if related_assets:
        return str(related_assets[0])
    spread_info = signal.get("spread_info")
    if isinstance(spread_info, dict) and spread_info.get("leg1") is not None:
        return str(spread_info["leg1"])
    return "MARKET"
