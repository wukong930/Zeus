from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.common import (
    AlertCreate,
    ContractCreate,
    CostSimulationRequest,
    HumanDecisionCreate,
    IndustryDataCreate,
    MarketDataCreate,
    NewsEventCreate,
    PositionCreate,
    RecommendationCreate,
    StrategyCreate,
    UserFeedbackCreate,
)


def test_common_write_payloads_reject_unknown_fields() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    cases = (
        (
            MarketDataCreate,
            {
                "market": "CN",
                "exchange": "SHFE",
                "commodity": "rebar",
                "symbol": "RB",
                "contract_month": "main",
                "timestamp": now,
                "open": 3200,
                "high": 3220,
                "low": 3180,
                "close": 3210,
                "volume": 1000,
            },
        ),
        (
            IndustryDataCreate,
            {
                "symbol": "RB",
                "data_type": "inventory",
                "value": 42,
                "unit": "kt",
                "source": "manual",
                "timestamp": now,
            },
        ),
        (ContractCreate, {"symbol": "RB", "contract_month": "2510"}),
        (
            AlertCreate,
            {
                "title": "RB alert",
                "summary": "test",
                "severity": "high",
                "category": "ferrous",
                "type": "momentum",
                "triggered_at": now,
                "confidence": 0.8,
            },
        ),
        (
            NewsEventCreate,
            {
                "source": "gdelt",
                "title": "Supply event",
                "published_at": now,
                "event_type": "supply",
                "direction": "bullish",
                "severity": 3,
                "time_horizon": "short",
                "llm_confidence": 0.7,
            },
        ),
        (HumanDecisionCreate, {"decision": "approve"}),
        (UserFeedbackCreate, {"agree": "agree", "will_trade": "will_trade"}),
        (CostSimulationRequest, {"inputs_by_symbol": {"RB": {"ore": 1.0}}}),
        (StrategyCreate, {"name": "s", "description": "d"}),
        (
            RecommendationCreate,
            {
                "recommended_action": "open",
                "priority_score": 80,
                "portfolio_fit_score": 70,
                "margin_efficiency_score": 75,
                "margin_required": 10_000,
                "reasoning": "test",
                "expires_at": now,
            },
        ),
        (
            PositionCreate,
            {
                "opened_at": now,
                "entry_spread": 100,
                "current_spread": 101,
                "spread_unit": "price",
                "unrealized_pnl": 10,
                "total_margin_used": 1000,
                "exit_condition": "manual_close",
                "target_z_score": 0,
                "current_z_score": 0,
                "half_life_days": 0,
                "days_held": 0,
            },
        ),
    )

    for schema, payload in cases:
        with pytest.raises(ValidationError):
            schema.model_validate({**payload, "unexpected_field": True})
