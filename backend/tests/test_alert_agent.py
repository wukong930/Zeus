from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.arbitration import require_human_decision_targets
from app.models.alert import Alert
from app.models.alert_agent import AlertAgentConfig, AlertDedupCache
from app.models.signal import SignalTrack
from app.schemas.common import HumanDecisionCreate
from app.services.alert_agent.classifier import classify_alert
from app.services.alert_agent.config import ConfidenceThresholds, load_confidence_thresholds
from app.services.alert_agent.dedup import check_alert_dedup, signal_direction
from app.services.alert_agent.human_decision import apply_decision_to_alert
from app.services.alert_agent.router import lacks_history, route_alert


class FailingSession:
    def __init__(self) -> None:
        self.rollback_count = 0

    async def scalars(self, _):
        raise RuntimeError("db failed")

    async def rollback(self) -> None:
        self.rollback_count += 1


class EmptyScalarResult:
    def first(self):
        return None


class SingleScalarResult:
    def __init__(self, row) -> None:
        self.row = row

    def first(self):
        return self.row


class ConfigSession:
    def __init__(self, value: dict) -> None:
        self.value = value

    async def scalars(self, _):
        return SingleScalarResult(AlertAgentConfig(key="confidence_thresholds", value=self.value))


class FailingSecondLookupSession:
    def __init__(self) -> None:
        self.scalars_count = 0
        self.rollback_count = 0

    async def scalars(self, _):
        self.scalars_count += 1
        if self.scalars_count == 2:
            raise RuntimeError("db failed")
        return EmptyScalarResult()

    async def rollback(self) -> None:
        self.rollback_count += 1


class TargetSession:
    def __init__(
        self,
        *,
        alert: Alert | None = None,
        signal_track: SignalTrack | None = None,
    ) -> None:
        self.alert = alert
        self.signal_track = signal_track

    async def get(self, model, _):
        if model is Alert:
            return self.alert
        if model is SignalTrack:
            return self.signal_track
        return None


def _decision_payload(**overrides) -> HumanDecisionCreate:
    values = {"decision": "approve"}
    values.update(overrides)
    return HumanDecisionCreate(**values)


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


async def test_confidence_threshold_config_ignores_invalid_values() -> None:
    thresholds = await load_confidence_thresholds(
        ConfigSession({"auto": "bad", "notify": None})  # type: ignore[arg-type]
    )

    assert thresholds == ConfidenceThresholds()


async def test_confidence_threshold_config_rejects_inverted_values() -> None:
    thresholds = await load_confidence_thresholds(
        ConfigSession({"auto": 0.5, "notify": 0.8})  # type: ignore[arg-type]
    )

    assert thresholds == ConfidenceThresholds()


async def test_lacks_history_rolls_back_after_lookup_failure() -> None:
    session = FailingSession()

    result = await lacks_history(
        session,  # type: ignore[arg-type]
        signal={"signal_type": "momentum"},
        context={"category": "ferrous", "regime": "normal"},
    )

    assert result is False
    assert session.rollback_count == 1


async def test_dedup_rolls_back_after_lookup_failure() -> None:
    session = FailingSession()

    decision = await check_alert_dedup(
        session,  # type: ignore[arg-type]
        signal={"signal_type": "momentum", "title": "RB bullish"},
        context={},
        score={"combined": 80},
    )

    assert decision.suppressed is False
    assert session.rollback_count == 1


async def test_dedup_rolls_back_after_combination_lookup_failure() -> None:
    session = FailingSecondLookupSession()

    decision = await check_alert_dedup(
        session,  # type: ignore[arg-type]
        signal={"signal_type": "momentum", "title": "RB bullish"},
        context={},
        score={"combined": 80},
        signal_combination_hash="combo-hash",
    )

    assert decision.suppressed is False
    assert session.scalars_count == 2
    assert session.rollback_count == 1


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


async def test_human_decision_target_validation_requires_a_target() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_human_decision_targets(TargetSession(), _decision_payload())

    assert exc_info.value.status_code == 400


async def test_human_decision_target_validation_rejects_missing_alert() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_human_decision_targets(
            TargetSession(),
            _decision_payload(alert_id=uuid4()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Alert not found"


async def test_human_decision_target_validation_rejects_missing_signal_track() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await require_human_decision_targets(
            TargetSession(),
            _decision_payload(signal_track_id=uuid4()),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Signal track not found"


async def test_human_decision_target_validation_accepts_existing_signal_track() -> None:
    signal_track = SignalTrack(
        id=uuid4(),
        signal_type="momentum",
        category="ferrous",
        confidence=0.7,
        outcome="pending",
    )

    await require_human_decision_targets(
        TargetSession(signal_track=signal_track),
        _decision_payload(signal_track_id=signal_track.id),
    )


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
