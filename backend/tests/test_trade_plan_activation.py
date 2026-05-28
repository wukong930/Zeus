from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.models.alert import Alert
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.services.trade_plans.activation import (
    ALERT_RESULT_CHANNELS,
    TradePlanActivationResult,
    actionable_scored_events_statement,
    alert_for_scored_event,
    alert_result_event_statement,
    alert_id_from_event,
    existing_recommendation_for_alert,
    live_trade_plan_scored_events,
    merge_open_trade_plan_duplicates,
    parse_payload_datetime,
    recommendation_for_alert_statement,
    scored_event_effective_at,
)


class FakeRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeMergeSession:
    def __init__(self, recommendations, alerts, linked_alerts) -> None:
        self.recommendations = recommendations
        self.alerts = {alert.id: alert for alert in alerts}
        self.linked_alerts = linked_alerts
        self.scalars_calls = 0
        self.flush_count = 0

    async def scalars(self, _):
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            return FakeRows(self.recommendations)
        return FakeRows(self.linked_alerts)

    async def get(self, model, row_id):
        if model is Alert:
            return self.alerts.get(row_id)
        return None

    async def flush(self) -> None:
        self.flush_count += 1


class FakeExistingSession:
    def __init__(self, recommendation) -> None:
        self.recommendation = recommendation

    async def scalar(self, _):
        return None

    async def get(self, model, row_id):
        if model is Recommendation and row_id == self.recommendation.id:
            return self.recommendation
        return None


class FakeAlertLookupSession:
    def __init__(self, event, alert) -> None:
        self.event = event
        self.alert = alert
        self.compiled_params = {}

    async def scalar(self, statement):
        self.compiled_params = statement.compile(dialect=postgresql.dialect()).params
        return self.event

    async def get(self, model, row_id):
        if model is Alert and row_id == self.alert.id:
            return self.alert
        return None


def test_trade_plan_activation_result_payload_is_scheduler_friendly() -> None:
    result = TradePlanActivationResult(scanned=3, created=1, skipped_stale=2)
    result.record_skip("stale_alert")
    result.record_skip("score_below_gate")
    result.record_skip("stale_alert")

    assert result.to_dict() == {
        "status": "completed",
        "scanned": 3,
        "created": 1,
        "linked_existing": 0,
        "linked_context": 0,
        "merged_duplicates": 0,
        "skipped_existing": 0,
        "skipped_missing_alert": 0,
        "skipped_ineligible": 0,
        "skipped_stale": 2,
        "skip_reasons": {
            "score_below_gate": 1,
            "stale_alert": 2,
        },
    }


def test_alert_id_from_event_parses_valid_payload_and_ignores_bad_payload() -> None:
    alert_id = uuid4()

    assert (
        alert_id_from_event(
            EventLog(
                event_id=uuid4(),
                channel="alert.created",
                source="test",
                correlation_id="corr",
                payload={"alert_id": str(alert_id)},
                status="published",
            )
        )
        == alert_id
    )
    assert (
        alert_id_from_event(
            EventLog(
                event_id=uuid4(),
                channel="alert.created",
                source="test",
                correlation_id="corr",
                payload={"alert_id": "not-a-uuid"},
                status="published",
            )
        )
        is None
    )


def test_actionable_scored_events_statement_limits_scan_to_trade_plan_window() -> None:
    statement = actionable_scored_events_statement(
        limit=25,
        as_of=datetime(2026, 5, 18, 12, tzinfo=timezone.utc),
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "event_log.channel = " in compiled
    assert "event_log.status = " in compiled
    assert "event_log.created_at >= " in compiled
    assert "ORDER BY event_log.created_at DESC, event_log.id DESC" in compiled
    assert "LIMIT " in compiled


def test_trade_plan_lookup_statements_use_stable_tie_breakers() -> None:
    alert_statement = alert_result_event_statement(
        correlation_id="corr-1",
        signal_type="spread_anomaly",
        symbol="RB2506",
    )
    alert_sql = _compile_postgres(alert_statement)
    recommendation_sql = _compile_postgres(recommendation_for_alert_statement(alert_id=uuid4()))

    assert "event_log.correlation_id =" in alert_sql
    assert "@>" in alert_sql
    assert "ORDER BY event_log.created_at DESC, event_log.id DESC" in alert_sql
    assert "recommendations.alert_id =" in recommendation_sql
    assert (
        "ORDER BY recommendations.created_at DESC, recommendations.id DESC"
        in recommendation_sql
    )
    assert ["RB"] in alert_statement.compile(dialect=postgresql.dialect()).params.values()


async def test_alert_for_scored_event_matches_contract_signal_to_root_alert_event() -> None:
    alert_id = uuid4()
    created_event = EventLog(
        event_id=uuid4(),
        channel="alert.created",
        source="test",
        correlation_id="corr-root-symbol",
        payload={
            "alert_id": str(alert_id),
            "signal_type": "inventory_shock",
            "related_assets": ["RU"],
        },
        status="handled",
    )
    scored_event = EventLog(
        event_id=uuid4(),
        channel="signal.scored",
        source="test",
        correlation_id="corr-root-symbol",
        payload={
            "signal": {
                "signal_type": "inventory_shock",
                "related_assets": [" ru2509 "],
            }
        },
        status="handled",
    )
    alert = Alert(
        id=alert_id,
        title="RU inventory shock",
        summary="Contract-level signal should recover the root-symbol alert event.",
        severity="high",
        category="rubber",
        type="inventory_shock",
        status="active",
        triggered_at=datetime.now(timezone.utc),
        confidence=0.8,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="notify",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["RU"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    session = FakeAlertLookupSession(created_event, alert)

    result = await alert_for_scored_event(session, scored_event)

    assert result is alert
    assert ["RU"] in session.compiled_params.values()


def test_live_trade_plan_scored_events_filters_by_effective_signal_time() -> None:
    as_of = datetime(2026, 5, 19, 6, tzinfo=timezone.utc)
    stale = EventLog(
        event_id=uuid4(),
        channel="signal.scored",
        source="test",
        correlation_id="stale",
        payload={"context": {"freshness_timestamp": "2026-05-17T16:00:00+00:00"}},
        status="handled",
        created_at=datetime(2026, 5, 19, 5, tzinfo=timezone.utc),
    )
    fresh = EventLog(
        event_id=uuid4(),
        channel="signal.scored",
        source="test",
        correlation_id="fresh",
        payload={"context": {"freshness_timestamp": "2026-05-18T16:00:00+00:00"}},
        status="handled",
        created_at=datetime(2026, 5, 19, 4, tzinfo=timezone.utc),
    )

    rows = live_trade_plan_scored_events([stale, fresh], limit=10, as_of=as_of)

    assert rows == [fresh]
    assert scored_event_effective_at(fresh) == datetime(2026, 5, 18, 16, tzinfo=timezone.utc)


def test_scored_event_effective_at_falls_back_to_created_at_for_bad_payload() -> None:
    created_at = datetime(2026, 5, 19, 4, tzinfo=timezone.utc)
    row = EventLog(
        event_id=uuid4(),
        channel="signal.scored",
        source="test",
        correlation_id="fallback",
        payload={"context": {"freshness_timestamp": "not-a-date"}},
        status="handled",
        created_at=created_at,
    )

    assert scored_event_effective_at(row) == created_at
    assert parse_payload_datetime("not-a-date") is None


def test_alert_result_channels_include_created_and_suppressed_alerts() -> None:
    assert ALERT_RESULT_CHANNELS == ("alert.created", "alert.suppressed")


async def test_existing_recommendation_for_alert_recovers_context_linked_plan() -> None:
    now = datetime.now(timezone.utc)
    recommendation = Recommendation(
        id=uuid4(),
        alert_id=uuid4(),
        status="pending_review",
        recommended_action="open_directional",
        legs=[{"asset": "I", "direction": "short", "lots": 1.0}],
        priority_score=44,
        portfolio_fit_score=75,
        margin_efficiency_score=80,
        margin_required=100000,
        reasoning="I short thesis.",
        risk_items=[],
        expires_at=now + timedelta(hours=8),
    )
    alert = Alert(
        id=uuid4(),
        title="I regime shift",
        summary="Context alert already linked to a plan.",
        severity="medium",
        category="ferrous",
        type="regime_shift",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.58,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="notify",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["I"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
        related_recommendation_id=recommendation.id,
    )

    existing = await existing_recommendation_for_alert(FakeExistingSession(recommendation), alert)

    assert existing is recommendation


async def test_merge_open_trade_plan_duplicates_links_alerts_and_ignores_duplicate() -> None:
    now = datetime(2026, 5, 20, tzinfo=timezone.utc)
    primary = Recommendation(
        id=uuid4(),
        alert_id=uuid4(),
        status="pending_review",
        recommended_action="open_directional",
        legs=[{"asset": "I", "direction": "short", "lots": 1.0}],
        priority_score=39,
        portfolio_fit_score=70,
        margin_efficiency_score=80,
        margin_required=100000,
        reasoning="Primary I short thesis.",
        risk_items=["Primary evidence."],
        expires_at=now + timedelta(hours=6),
        backtest_summary={"signal_type": "median_pressure"},
    )
    duplicate_alert = Alert(
        id=uuid4(),
        title="I capacity contraction risk",
        summary="Duplicate I short evidence.",
        severity="high",
        category="ferrous",
        type="capacity_contraction",
        status="pending",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=True,
        llm_involved=True,
        confidence_tier="notify",
        human_action_required=True,
        dedup_suppressed=False,
        related_assets=["I"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )
    duplicate = Recommendation(
        id=uuid4(),
        alert_id=duplicate_alert.id,
        status="pending_review",
        recommended_action="open_directional",
        legs=[{"asset": "I", "direction": "short", "lots": 1.0}],
        priority_score=44,
        portfolio_fit_score=75,
        margin_efficiency_score=81,
        margin_required=120000,
        reasoning="Supporting I short thesis.",
        risk_items=["Supporting evidence."],
        expires_at=now + timedelta(hours=12),
        backtest_summary={"signal_type": "capacity_contraction"},
    )
    linked_alert = Alert(
        id=uuid4(),
        title="I linked alert",
        summary="Already linked to duplicate.",
        severity="high",
        category="ferrous",
        type="median_pressure",
        status="pending",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="notify",
        human_action_required=True,
        dedup_suppressed=False,
        related_assets=["I"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
        related_recommendation_id=duplicate.id,
    )
    session = FakeMergeSession(
        [primary, duplicate],
        [duplicate_alert],
        [linked_alert],
    )

    merged = await merge_open_trade_plan_duplicates(session, as_of=now)

    assert merged == 1
    assert primary.priority_score == 44
    assert primary.backtest_summary["merged_evidence"] is True
    assert duplicate.status == "ignored"
    assert duplicate.ignored_reason == f"Merged into active recommendation {primary.id}."
    assert duplicate.backtest_summary["merged_into_recommendation_id"] == str(primary.id)
    assert duplicate_alert.related_recommendation_id == primary.id
    assert linked_alert.related_recommendation_id == primary.id
    assert session.flush_count == 1


def _compile_postgres(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))
