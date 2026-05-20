from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.events import ZeusEvent
from app.models.alert import Alert
from app.models.recommendation import Recommendation
from app.services.pipeline.handlers import (
    attach_trade_plan_context_evidence,
    build_trade_plan_recommendation,
    compact_trade_plan_risk_items,
    evaluate_trade_plan_candidate,
    handle_market_update,
    handle_news_event,
    handle_signal_detected,
    handle_signal_scored,
    merge_trade_plan_evidence,
    open_trade_plan_for_context_signal,
    recommended_action,
    trade_plan_matches,
)


class CapturingPublisher:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def __call__(self, channel: str, payload: dict, **kwargs) -> ZeusEvent:
        event = ZeusEvent(
            channel=channel,
            payload=payload,
            source=kwargs.get("source", "test"),
            correlation_id=kwargs.get("correlation_id"),
        )
        self.calls.append({"event": event, "kwargs": kwargs})
        return event


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def scalars(self, _):
        return FakeScalars()

    async def flush(self) -> None:
        self.flush_count += 1


class FakeScalars:
    def first(self):
        return None


class FakeRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeOpenPlanSession:
    def __init__(self, rows) -> None:
        self.rows = rows

    async def scalars(self, _):
        return FakeRows(self.rows)


def _market_update_event() -> ZeusEvent:
    return ZeusEvent(
        channel="market.update",
        payload={
            "contexts": [
                {
                    "symbol1": "RB",
                    "symbol2": "HC",
                    "category": "ferrous",
                    "regime": "range_low_vol",
                    "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                    "spread_stats": {
                        "adf_p_value": 0.03,
                        "half_life": 12,
                        "spread_mean": 10,
                        "spread_std_dev": 2,
                        "current_z_score": 2.8,
                    },
                }
            ]
        },
        source="test",
    )


async def test_market_update_handler_publishes_detected_signals() -> None:
    publisher = CapturingPublisher()

    published = await handle_market_update(_market_update_event(), publisher=publisher)

    assert [event.channel for event in published] == ["signal.detected", "signal.detected"]
    assert publisher.calls[0]["event"].payload["signal"]["signal_type"] == "spread_anomaly"
    assert publisher.calls[0]["event"].payload["context"]["symbol1"] == "RB"
    assert publisher.calls[0]["event"].payload["context"]["regime"] == "range_low_vol"


async def test_market_update_handler_skips_malformed_contexts() -> None:
    event = _market_update_event()
    valid_context = event.payload["contexts"][0]
    event.payload["contexts"] = [
        {"symbol1": "RB", "category": "ferrous", "timestamp": "not-a-date"},
        valid_context,
    ]
    publisher = CapturingPublisher()

    published = await handle_market_update(event, publisher=publisher)

    assert [item.channel for item in published] == ["signal.detected", "signal.detected"]
    assert all(call["event"].payload["context"]["symbol1"] == "RB" for call in publisher.calls)


async def test_news_event_handler_publishes_news_signal() -> None:
    event = ZeusEvent(
        channel="news.event",
        payload={
            "news_event": {
                "id": "evt-1",
                "source": "cailianshe",
                "title": "OPEC+ extends production cuts",
                "summary": "OPEC+ extends production cuts, bullish for crude oil.",
                "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                "event_type": "supply",
                "affected_symbols": ["SC"],
                "direction": "bullish",
                "severity": 5,
                "time_horizon": "medium",
                "llm_confidence": 0.82,
                "source_count": 2,
                "verification_status": "cross_verified",
                "requires_manual_confirmation": False,
            },
            "contexts": [
                {
                    "symbol1": "SC",
                    "category": "energy",
                    "regime": "news",
                    "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                    "news_events": [
                        {
                            "id": "evt-1",
                            "source": "cailianshe",
                            "title": "OPEC+ extends production cuts",
                            "summary": "OPEC+ extends production cuts, bullish for crude oil.",
                            "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                            "event_type": "supply",
                            "affected_symbols": ["SC"],
                            "direction": "bullish",
                            "severity": 5,
                            "time_horizon": "medium",
                            "llm_confidence": 0.82,
                            "source_count": 2,
                            "verification_status": "cross_verified",
                            "requires_manual_confirmation": False,
                        }
                    ],
                }
            ],
        },
        source="test",
    )
    publisher = CapturingPublisher()

    published = await handle_news_event(event, publisher=publisher)

    assert [item.channel for item in published] == ["signal.detected"]
    assert publisher.calls[0]["event"].payload["signal"]["signal_type"] == "news_event"
    assert publisher.calls[0]["event"].payload["context"]["news_events"][0]["id"] == "evt-1"


async def test_news_event_handler_skips_malformed_contexts() -> None:
    event_payload = {
        "id": "evt-1",
        "source": "cailianshe",
        "title": "OPEC+ extends production cuts",
        "summary": "OPEC+ extends production cuts, bullish for crude oil.",
        "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
        "event_type": "supply",
        "affected_symbols": ["SC"],
        "direction": "bullish",
        "severity": 5,
        "time_horizon": "medium",
        "llm_confidence": 0.82,
        "source_count": 2,
        "verification_status": "cross_verified",
        "requires_manual_confirmation": False,
    }
    event = ZeusEvent(
        channel="news.event",
        payload={
            "news_event": event_payload,
            "contexts": [
                {"symbol1": "SC", "category": "energy", "timestamp": "bad-time"},
                {
                    "symbol1": "SC",
                    "category": "energy",
                    "regime": "news",
                    "timestamp": event_payload["published_at"],
                    "news_events": [event_payload],
                },
            ],
        },
        source="test",
    )
    publisher = CapturingPublisher()

    published = await handle_news_event(event, publisher=publisher)

    assert [item.channel for item in published] == ["signal.detected"]
    assert publisher.calls[0]["event"].payload["signal"]["signal_type"] == "news_event"


async def test_news_event_handler_publishes_rubber_supply_signal() -> None:
    event_payload = {
        "id": "rubber-evt-1",
        "source": "rubber_supply_gdelt",
        "title": "Thailand floods disrupt natural rubber tapping",
        "summary": "Heavy rainfall in southern Thailand disrupts rubber tapping and exports.",
        "published_at": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
        "event_type": "weather",
        "affected_symbols": ["NR", "RU"],
        "direction": "bullish",
        "severity": 4,
        "time_horizon": "short",
        "llm_confidence": 0.78,
        "source_count": 2,
        "verification_status": "cross_verified",
        "requires_manual_confirmation": False,
    }
    event = ZeusEvent(
        channel="news.event",
        payload={
            "news_event": event_payload,
            "contexts": [
                {
                    "symbol1": "RU",
                    "category": "rubber",
                    "regime": "news",
                    "timestamp": event_payload["published_at"],
                    "news_events": [event_payload],
                }
            ],
        },
        source="test",
    )
    publisher = CapturingPublisher()

    published = await handle_news_event(event, publisher=publisher)

    assert [item.channel for item in published] == ["signal.detected", "signal.detected"]
    assert [call["event"].payload["signal"]["signal_type"] for call in publisher.calls] == [
        "news_event",
        "rubber_supply_shock",
    ]


async def test_signal_detected_handler_publishes_score() -> None:
    publisher = CapturingPublisher()
    detected = (await handle_market_update(_market_update_event(), publisher=publisher))[0]
    score_publisher = CapturingPublisher()

    scored = await handle_signal_detected(
        detected,
        publisher=score_publisher,
    )

    assert scored is not None
    assert scored.channel == "signal.scored"
    assert scored.payload["recommended_action"] == "open_spread"
    assert scored.payload["score"]["priority"] > 0
    assert scored.payload["adversarial_result"]["passed"] is True
    assert scored.payload["legs"][0]["asset"] == "RB"


def test_directional_signal_can_generate_review_trade_plan_from_legacy_watchlist_payload() -> None:
    now = datetime.now(timezone.utc)
    signal = {
        "signal_type": "capacity_contraction",
        "severity": "high",
        "confidence": 0.95,
        "title": "I capacity contraction risk",
        "summary": "I margins stayed below -5%; bearish supply contraction pressure is building.",
        "related_assets": ["I"],
        "risk_items": ["Bearish capacity contraction risk."],
        "manual_check_items": ["Validate operating-rate and inventory changes."],
    }
    alert = Alert(
        id=uuid4(),
        title="I capacity contraction risk",
        summary="Bearish cost signal",
        severity="high",
        category="ferrous",
        type="capacity_contraction",
        status="pending",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.95,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=True,
        dedup_suppressed=False,
        related_assets=["I"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    recommendation = build_trade_plan_recommendation(
        alert=alert,
        signal=signal,
        context={"category": "ferrous", "market_data": [{"close": 797.0}]},
        score={"combined": 64, "priority": 44, "portfolio_fit": 75, "margin_efficiency": 80},
        event_payload={
            "recommended_action": "watchlist_only",
            "adversarial_result": {"passed": True},
            "legs": [{"asset": "I", "direction": "watch"}],
        },
        triggered_at=now,
    )

    assert recommended_action(signal) == "open_directional"
    assert recommendation is not None
    assert recommendation.recommended_action == "open_directional"
    assert recommendation.status == "pending_review"
    assert recommendation.legs == [{"asset": "I", "direction": "short", "lots": 1.0}]
    assert recommendation.entry_price == 797.0
    assert recommendation.backtest_summary is not None
    assert recommendation.backtest_summary["recommended_action"] == "open_directional"
    assert recommendation.backtest_summary["review_required"] is True
    assert "Alert Agent 标记需要人工复核" in recommendation.backtest_summary["review_reasons"]
    assert any("复核原因" in item for item in recommendation.risk_items)


def test_trade_plan_candidate_evaluation_reports_score_gate_reason() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="RB weak momentum",
        summary="Below gate.",
        severity="high",
        category="ferrous",
        type="momentum",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["RB"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal={
            "signal_type": "momentum",
            "severity": "high",
            "confidence": 0.9,
            "title": "RB bullish momentum",
            "summary": "Bullish momentum signal.",
            "related_assets": ["RB"],
        },
        context={"category": "ferrous", "market_data": [{"close": 3250.0}]},
        score={"combined": 55, "priority": 55},
        event_payload={"recommended_action": "watchlist_only", "adversarial_result": {"passed": True}},
        triggered_at=now,
    )

    assert evaluation.passed is False
    assert evaluation.recommendation is None
    assert evaluation.skip_reason == "score_below_gate"


def test_trade_plan_candidate_evaluation_reports_missing_price_reason() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="RB strong momentum",
        summary="No price.",
        severity="high",
        category="ferrous",
        type="momentum",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["RB"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal={
            "signal_type": "momentum",
            "severity": "high",
            "confidence": 0.9,
            "title": "RB bullish momentum",
            "summary": "Bullish momentum signal.",
            "related_assets": ["RB"],
        },
        context={"category": "ferrous", "market_data": []},
        score={"combined": 85, "priority": 85},
        event_payload={"recommended_action": "watchlist_only", "adversarial_result": {"passed": True}},
        triggered_at=now,
    )

    assert evaluation.passed is False
    assert evaluation.skip_reason == "missing_entry_price"


def test_directional_candidate_below_confidence_reports_score_gate_reason() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="MA bullish momentum",
        summary="Below directional confidence gate.",
        severity="high",
        category="chemical",
        type="momentum",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.6,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["MA"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal={
            "signal_type": "momentum",
            "severity": "high",
            "confidence": 0.6,
            "title": "MA bullish momentum",
            "summary": "Bullish moving-average crossover.",
            "related_assets": ["MA"],
        },
        context={"category": "chemical", "market_data": [{"close": 5116.0}]},
        score={"combined": 85, "priority": 85},
        event_payload={"recommended_action": "watchlist_only", "adversarial_result": {"passed": True}},
        triggered_at=now,
    )

    assert recommended_action(
        {
            "signal_type": "momentum",
            "confidence": 0.6,
            "title": "MA bullish momentum",
            "summary": "Bullish moving-average crossover.",
            "related_assets": ["MA"],
        }
    ) == "open_directional"
    assert evaluation.passed is False
    assert evaluation.skip_reason == "score_below_gate"


def test_warmup_adversarial_result_allows_trade_plan_candidate() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="MA bullish momentum",
        summary="Warmup adversarial result should not block production flow.",
        severity="high",
        category="chemical",
        type="momentum",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=False,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["MA"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal={
            "signal_type": "momentum",
            "severity": "high",
            "confidence": 0.9,
            "direction": "bullish",
            "title": "MA bullish momentum",
            "summary": "Bullish moving-average crossover.",
            "related_assets": ["MA"],
        },
        context={"category": "chemical", "market_data": [{"close": 5116.0}]},
        score={"combined": 85, "priority": 85, "portfolio_fit": 75, "margin_efficiency": 80},
        event_payload={
            "recommended_action": "watchlist_only",
            "adversarial_result": {
                "passed": False,
                "suppressed": False,
                "warmup_enabled": True,
                "runtime_mode": "warmup",
            },
        },
        triggered_at=now,
    )

    assert evaluation.passed is True
    assert evaluation.recommendation is not None
    assert evaluation.recommendation.recommended_action == "open_directional"
    assert any("Adversarial engine warmup" in item for item in evaluation.recommendation.risk_items)


def test_warmup_confidence_penalty_is_restored_for_trade_plan_gate() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="I capacity contraction risk",
        summary="Legacy warmup payload carried a confidence penalty.",
        severity="high",
        category="ferrous",
        type="capacity_contraction",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.6,
        adversarial_passed=False,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["I"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal={
            "signal_type": "capacity_contraction",
            "severity": "high",
            "confidence": 0.6,
            "direction": "bearish",
            "title": "I capacity contraction risk",
            "summary": "Bearish cost-model signal.",
            "related_assets": ["I"],
        },
        context={"category": "ferrous", "market_data": [{"close": 797.0}]},
        score={"combined": 62, "priority": 40, "portfolio_fit": 75, "margin_efficiency": 80},
        event_payload={
            "recommended_action": "watchlist_only",
            "adversarial_result": {
                "passed": False,
                "suppressed": False,
                "warmup_enabled": True,
                "runtime_mode": "warmup",
                "confidence_multiplier": 0.7,
            },
        },
        triggered_at=now,
    )

    assert evaluation.passed is True
    assert evaluation.recommendation is not None
    assert evaluation.recommendation.recommended_action == "open_directional"
    assert evaluation.recommendation.backtest_summary is not None
    assert round(evaluation.recommendation.backtest_summary["effective_confidence"], 4) == 0.8571
    assert any(
        "Warmup confidence restored for trade-plan gating" in item
        for item in evaluation.recommendation.risk_items
    )


def test_trade_plan_match_and_merge_combines_same_symbol_direction_evidence() -> None:
    now = datetime.now(timezone.utc)
    primary_alert_id = uuid4()
    target = Recommendation(
        id=uuid4(),
        alert_id=primary_alert_id,
        status="pending_review",
        recommended_action="open_directional",
        legs=[{"asset": "I", "direction": "short", "lots": 1.0}],
        priority_score=39,
        portfolio_fit_score=70,
        margin_efficiency_score=80,
        margin_required=100000,
        reasoning="Primary I short thesis.",
        risk_items=["Primary evidence."],
        expires_at=now + timedelta(hours=8),
        backtest_summary={"signal_type": "median_pressure"},
    )
    incoming = Recommendation(
        id=uuid4(),
        alert_id=uuid4(),
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
    alert = Alert(
        id=incoming.alert_id,
        title="I capacity contraction risk",
        summary="Supporting cost-model signal.",
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

    assert trade_plan_matches(target, incoming) is True

    merge_trade_plan_evidence(target, incoming, alert=alert)

    assert target.priority_score == 44
    assert target.portfolio_fit_score == 75
    assert target.margin_efficiency_score == 81
    assert target.margin_required == 120000
    assert target.expires_at == incoming.expires_at
    assert target.risk_items == ["Primary evidence.", "Supporting evidence."]
    assert target.backtest_summary is not None
    assert target.backtest_summary["merged_evidence"] is True
    assert target.backtest_summary["evidence_count"] == 2
    assert target.backtest_summary["evidence_signal_types"] == [
        "capacity_contraction",
        "median_pressure",
    ]
    assert target.backtest_summary["linked_supporting_alerts"][0]["alert_id"] == str(alert.id)


def test_compact_trade_plan_risk_items_preserves_order_and_caps_response_limit() -> None:
    items = compact_trade_plan_risk_items(
        ["primary", "duplicate", "duplicate"],
        [f"context-{index}" for index in range(30)],
    )

    assert items[:3] == ["primary", "duplicate", "context-0"]
    assert len(items) == 20


async def test_context_signal_links_to_single_open_symbol_plan_without_changing_scores() -> None:
    now = datetime.now(timezone.utc)
    plan = Recommendation(
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
        risk_items=["Primary cost evidence."],
        expires_at=now + timedelta(hours=8),
        backtest_summary={"signal_type": "capacity_contraction"},
    )
    session = FakeOpenPlanSession([plan])
    signal = {
        "signal_type": "regime_shift",
        "severity": "medium",
        "confidence": 0.58,
        "title": "I regime shift",
        "summary": "I regime changed.",
        "related_assets": ["I"],
        "risk_items": ["Mean-reversion assumptions may need review."],
    }
    alert = Alert(
        id=uuid4(),
        title="I regime shift",
        summary="I regime changed.",
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
    )

    linked_plan = await open_trade_plan_for_context_signal(session, signal, as_of=now)

    assert linked_plan is plan
    attach_trade_plan_context_evidence(
        plan,
        alert=alert,
        signal=signal,
        skip_reason="unsupported_action",
    )

    assert plan.priority_score == 44
    assert plan.backtest_summary["context_enriched"] is True
    assert plan.backtest_summary["context_evidence_count"] == 1
    assert plan.backtest_summary["context_signal_types"] == ["regime_shift"]
    assert plan.backtest_summary["linked_context_alerts"][0]["skip_reason"] == "unsupported_action"
    assert "Mean-reversion assumptions may need review." in plan.risk_items


async def test_context_signal_does_not_link_when_symbol_has_conflicting_open_directions() -> None:
    now = datetime.now(timezone.utc)
    long_plan = Recommendation(
        id=uuid4(),
        alert_id=uuid4(),
        status="pending_review",
        recommended_action="open_directional",
        legs=[{"asset": "I", "direction": "long", "lots": 1.0}],
        priority_score=44,
        portfolio_fit_score=75,
        margin_efficiency_score=80,
        margin_required=100000,
        reasoning="I long thesis.",
        risk_items=[],
        expires_at=now + timedelta(hours=8),
    )
    short_plan = Recommendation(
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

    linked_plan = await open_trade_plan_for_context_signal(
        FakeOpenPlanSession([long_plan, short_plan]),
        {
            "signal_type": "regime_shift",
            "confidence": 0.58,
            "title": "I regime shift",
            "summary": "I regime changed.",
            "related_assets": ["I"],
        },
        as_of=now,
    )

    assert linked_plan is None


def test_structured_direction_drives_directional_candidate_without_text_markers() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="RB event impact",
        summary="Structured event impact.",
        severity="high",
        category="ferrous",
        type="news_event",
        status="pending",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=True,
        dedup_suppressed=False,
        related_assets=["RB"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    recommendation = build_trade_plan_recommendation(
        alert=alert,
        signal={
            "signal_type": "news_event",
            "severity": "high",
            "confidence": 0.9,
            "direction": "bearish",
            "title": "RB event impact",
            "summary": "Structured event impact.",
            "related_assets": ["RB"],
        },
        context={"category": "ferrous", "market_data": [{"close": 3210.0}]},
        score={"combined": 82, "priority": 82, "portfolio_fit": 75, "margin_efficiency": 80},
        event_payload={"recommended_action": "watchlist_only", "adversarial_result": {"passed": True}},
        triggered_at=now,
    )

    assert recommendation is not None
    assert recommendation.recommended_action == "open_directional"
    assert recommendation.legs == [{"asset": "RB", "direction": "short", "lots": 1.0}]


def test_directional_candidate_without_direction_reports_missing_direction() -> None:
    now = datetime.now(timezone.utc)
    alert = Alert(
        id=uuid4(),
        title="AG inventory shock",
        summary="Range and volatility expanded without a price direction.",
        severity="high",
        category="precious_metals",
        type="inventory_shock",
        status="active",
        triggered_at=now,
        expires_at=now + timedelta(days=1),
        confidence=0.9,
        adversarial_passed=True,
        llm_involved=False,
        confidence_tier="auto",
        human_action_required=False,
        dedup_suppressed=False,
        related_assets=["AG"],
        trigger_chain=[],
        risk_items=[],
        manual_check_items=[],
    )

    evaluation = evaluate_trade_plan_candidate(
        alert=alert,
        signal={
            "signal_type": "inventory_shock",
            "severity": "high",
            "confidence": 0.9,
            "title": "AG inventory shock",
            "summary": "Range and volatility expanded.",
            "related_assets": ["AG"],
        },
        context={"category": "precious_metals", "market_data": [{"close": 6494.0}]},
        score={"combined": 85, "priority": 85},
        event_payload={"recommended_action": "watchlist_only", "adversarial_result": {"passed": True}},
        triggered_at=now,
    )

    assert evaluation.passed is False
    assert evaluation.skip_reason == "missing_direction"


async def test_signal_scored_handler_creates_alert_and_publishes_event() -> None:
    signal_publisher = CapturingPublisher()
    detected = (await handle_market_update(_market_update_event(), publisher=signal_publisher))[0]
    score_publisher = CapturingPublisher()
    scored = await handle_signal_detected(detected, publisher=score_publisher)
    assert scored is not None

    session = FakeSession()
    alert_publisher = CapturingPublisher()
    created = await handle_signal_scored(
        scored,
        session=session,  # type: ignore[arg-type]
        publisher=alert_publisher,
    )

    assert created is not None
    assert created.channel == "alert.created"
    alert = next(row for row in session.rows if isinstance(row, Alert))
    assert alert.type == "spread_anomaly"
    assert alert.adversarial_passed is True
    assert created.payload["adversarial_passed"] is True
    assert created.payload["alert_id"] == str(alert.id)


async def test_signal_scored_handler_creates_review_trade_plan_for_actionable_spread() -> None:
    signal_publisher = CapturingPublisher()
    event = _market_update_event()
    event.payload["contexts"][0]["timestamp"] = datetime.now(timezone.utc).isoformat()
    detected = (await handle_market_update(event, publisher=signal_publisher))[0]
    score_publisher = CapturingPublisher()
    scored = await handle_signal_detected(detected, publisher=score_publisher)
    assert scored is not None

    session = FakeSession()
    alert_publisher = CapturingPublisher()
    created = await handle_signal_scored(
        scored,
        session=session,  # type: ignore[arg-type]
        publisher=alert_publisher,
    )

    assert created is not None
    alert = next(row for row in session.rows if isinstance(row, Alert))
    recommendation = next(row for row in session.rows if isinstance(row, Recommendation))
    assert recommendation.status == "pending_review"
    assert recommendation.alert_id == alert.id
    assert alert.related_recommendation_id == recommendation.id
    assert recommendation.recommended_action == "open_spread"
    assert [leg["direction"] for leg in recommendation.legs] == ["short", "long"]
    assert recommendation.priority_score >= 80
    assert recommendation.entry_price > 0
    assert recommendation.stop_loss is not None
    assert recommendation.take_profit is not None
    assert created.payload["recommendation_id"] == str(recommendation.id)
    recommendation_event = next(
        call["event"] for call in alert_publisher.calls if call["event"].channel == "recommendation.created"
    )
    assert recommendation_event.payload["recommendation_id"] == str(recommendation.id)


async def test_signal_scored_handler_skips_trade_plan_for_stale_spread_signal() -> None:
    signal_publisher = CapturingPublisher()
    detected = (await handle_market_update(_market_update_event(), publisher=signal_publisher))[0]
    score_publisher = CapturingPublisher()
    scored = await handle_signal_detected(detected, publisher=score_publisher)
    assert scored is not None

    session = FakeSession()
    alert_publisher = CapturingPublisher()
    created = await handle_signal_scored(
        scored,
        session=session,  # type: ignore[arg-type]
        publisher=alert_publisher,
    )

    assert created is not None
    assert next((row for row in session.rows if isinstance(row, Recommendation)), None) is None
    assert created.payload["recommendation_id"] is None


async def test_signal_scored_handler_uses_context_freshness_timestamp_for_daily_bars() -> None:
    signal_publisher = CapturingPublisher()
    event = _market_update_event()
    event.payload["contexts"][0]["timestamp"] = datetime(2026, 5, 18, tzinfo=timezone.utc).isoformat()
    event.payload["contexts"][0]["freshness_timestamp"] = datetime.now(timezone.utc).isoformat()
    detected = (await handle_market_update(event, publisher=signal_publisher))[0]
    score_publisher = CapturingPublisher()
    scored = await handle_signal_detected(detected, publisher=score_publisher)
    assert scored is not None

    session = FakeSession()
    alert_publisher = CapturingPublisher()
    created = await handle_signal_scored(
        scored,
        session=session,  # type: ignore[arg-type]
        publisher=alert_publisher,
    )

    assert created is not None
    alert = next(row for row in session.rows if isinstance(row, Alert))
    recommendation = next(row for row in session.rows if isinstance(row, Recommendation))
    assert alert.triggered_at.isoformat() == event.payload["contexts"][0]["freshness_timestamp"]
    assert recommendation.expires_at > datetime.now(timezone.utc)
    assert created.payload["recommendation_id"] == str(recommendation.id)


async def test_signal_scored_handler_requests_scenario_for_arbitration_route() -> None:
    event = ZeusEvent(
        channel="signal.scored",
        payload={
            "signal": {
                "signal_type": "momentum",
                "severity": "high",
                "confidence": 0.72,
                "title": "RB bullish signal with bearish inventory conflict",
                "summary": "Momentum is bullish while inventory pressure is bearish.",
                "related_assets": ["RB"],
                "risk_items": [],
                "manual_check_items": [],
            },
            "context": {
                "category": "ferrous",
                "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                "market_data": [{"close": 3250}],
            },
            "score": {"priority": 75, "combined": 75},
        },
        source="test",
    )
    session = FakeSession()
    publisher = CapturingPublisher()

    created = await handle_signal_scored(
        event,
        session=session,  # type: ignore[arg-type]
        publisher=publisher,
    )

    assert created is not None
    assert created.channel == "alert.created"
    requested = next(call["event"] for call in publisher.calls if call["event"].channel == "scenario.requested")
    assert requested.payload["request"]["target_symbol"] == "RB"
    assert requested.payload["request"]["shocks"] == {"RB": 0.08}
    assert requested.payload["request"]["base_price"] == 3250
    assert requested.payload["trigger"]["route"] == "arbitrate"


async def test_signal_scored_handler_does_not_create_trade_plan_for_watchlist_signal() -> None:
    event = ZeusEvent(
        channel="signal.scored",
        payload={
            "signal": {
                "signal_type": "momentum",
                "severity": "high",
                "confidence": 0.82,
                "title": "RB momentum watch",
                "summary": "Momentum is strong but not a spread trade.",
                "related_assets": ["RB"],
                "risk_items": [],
                "manual_check_items": [],
            },
            "context": {
                "category": "ferrous",
                "timestamp": datetime(2026, 5, 3, tzinfo=timezone.utc).isoformat(),
                "market_data": [{"close": 3250}],
            },
            "score": {"priority": 85, "combined": 85},
            "recommended_action": "watchlist_only",
            "adversarial_result": {"passed": True},
            "legs": [{"asset": "RB", "direction": "watch"}],
        },
        source="test",
    )
    session = FakeSession()
    publisher = CapturingPublisher()

    created = await handle_signal_scored(
        event,
        session=session,  # type: ignore[arg-type]
        publisher=publisher,
    )

    assert created is not None
    assert next((row for row in session.rows if isinstance(row, Recommendation)), None) is None
    assert all(call["event"].channel != "recommendation.created" for call in publisher.calls)
    assert created.payload["recommendation_id"] is None
