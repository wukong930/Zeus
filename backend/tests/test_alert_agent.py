from datetime import datetime, timezone

from app.models.alert import Alert
from app.models.alert_agent import AlertDedupCache
from app.services.alert_agent.classifier import classify_alert
from app.services.alert_agent.dedup import signal_direction
from app.services.alert_agent.human_decision import apply_decision_to_alert
from app.services.alert_agent.router import route_alert


def test_classifier_marks_spread_signal_as_l3() -> None:
    signal = {
        "signal_type": "spread_anomaly",
        "severity": "high",
        "spread_info": {"leg1": "RB", "leg2": "HC"},
        "related_assets": ["RB", "HC"],
    }

    assert classify_alert(signal, {"priority": 70, "combined": 70}) == "L3"


async def test_router_sends_conflict_to_arbitration() -> None:
    decision = await route_alert(
        None,
        signal={
            "signal_type": "momentum",
            "confidence": 0.72,
            "severity": "medium",
            "title": "RB bullish but bearish risk",
            "summary": "Momentum is bullish while inventory is bearish.",
            "risk_items": [],
            "related_assets": ["RB"],
        },
        context={"category": "ferrous"},
        score={"priority": 60, "combined": 60},
    )

    assert decision.route == "arbitrate"
    assert decision.human_action_required is True
    assert decision.human_action_deadline is not None


async def test_router_requires_confirmation_for_low_confidence() -> None:
    decision = await route_alert(
        None,
        signal={
            "signal_type": "news_event",
            "confidence": 0.55,
            "severity": "medium",
            "title": "SC supply event",
            "summary": "Supply event needs confirmation.",
            "risk_items": [],
            "related_assets": ["SC"],
        },
        context={"category": "energy"},
        score={"priority": 50, "combined": 50},
    )

    assert decision.confidence_tier == "confirm"
    assert decision.route == "confirm"
    assert decision.human_action_required is True


def test_signal_direction_extracts_bullish_and_bearish_text() -> None:
    assert signal_direction({"title": "RB bullish momentum", "risk_items": []}) == "bullish"
    assert signal_direction({"title": "RB bearish inventory", "risk_items": []}) == "bearish"


def test_human_decision_updates_alert_without_weight_changes() -> None:
    alert = Alert(
        title="RB confirm signal",
        summary="Needs human confirmation.",
        severity="medium",
        category="ferrous",
        type="momentum",
        status="pending",
        triggered_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        confidence=0.55,
        related_assets=["RB"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
        human_action_required=True,
    )

    apply_decision_to_alert(alert, "approve", confidence_override=0.72)

    assert alert.status == "active"
    assert alert.confidence == 0.72
    assert alert.human_action_required is False


def test_alert_dedup_cache_model_keeps_symbol_direction_key() -> None:
    row = AlertDedupCache(
        symbol="RB",
        direction="bullish",
        evaluator="momentum",
        last_emitted_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        last_severity="medium",
    )

    assert row.symbol == "RB"
    assert row.direction == "bullish"
    assert row.evaluator == "momentum"
