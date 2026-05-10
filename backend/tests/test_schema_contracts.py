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
from app.schemas.event_intelligence import EventIntelligenceCreate


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
        (
            EventIntelligenceCreate,
            {
                "source_type": "news_event",
                "source_id": "news-1",
                "title": "Rubber weather risk",
                "summary": "Rainfall affects tapping.",
                "event_type": "weather",
                "event_timestamp": now,
            },
        ),
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


def test_alert_payload_normalizes_related_assets() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    payload = AlertCreate.model_validate(
        {
            "title": "RB alert",
            "summary": "test",
            "severity": "high",
            "category": "ferrous",
            "type": "momentum",
            "triggered_at": now,
            "confidence": 0.8,
            "related_assets": [" rb ", "RB", " sc "],
        }
    )

    assert payload.related_assets == ["RB", "SC"]


def test_alert_payload_bounds_core_fields() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
        "title": "RB alert",
        "summary": "test",
        "severity": "high",
        "category": "ferrous",
        "type": "momentum",
        "triggered_at": now,
        "confidence": 0.8,
    }

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "title": "x" * 301})

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "severity": "urgent"})

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "category": "x" * 21})

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "confidence": 1.1})

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "confidence_tier": "escalate"})


def test_alert_payload_bounds_json_and_list_fields() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
        "title": "RB alert",
        "summary": "test",
        "severity": "high",
        "category": "ferrous",
        "type": "momentum",
        "triggered_at": now,
        "confidence": 0.8,
    }

    with pytest.raises(ValidationError):
        AlertCreate.model_validate(
            {
                **base_payload,
                "related_assets": [f"RB{index}" for index in range(21)],
            }
        )

    with pytest.raises(ValidationError):
        AlertCreate.model_validate(
            {
                **base_payload,
                "spread_info": {"bad": object()},
            }
        )

    with pytest.raises(ValidationError):
        AlertCreate.model_validate(
            {
                **base_payload,
                "trigger_chain": [{"step": index} for index in range(31)],
            }
        )

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "risk_items": ["x" * 801]})

    with pytest.raises(ValidationError):
        AlertCreate.model_validate({**base_payload, "manual_check_items": ["x" * 801]})


def test_human_decision_payload_rejects_oversized_json() -> None:
    with pytest.raises(ValidationError):
        HumanDecisionCreate.model_validate(
            {
                "decision": "approve",
                "payload": {f"key_{index}": index for index in range(41)},
            }
        )


def test_human_decision_payload_rejects_non_json_values() -> None:
    with pytest.raises(ValidationError):
        HumanDecisionCreate.model_validate(
            {
                "decision": "approve",
                "payload": {"bad": object()},
            }
        )


def test_human_decision_text_fields_are_bounded() -> None:
    with pytest.raises(ValidationError):
        HumanDecisionCreate.model_validate(
            {
                "decision": "approve",
                "decided_by": "x" * 81,
            }
        )

    with pytest.raises(ValidationError):
        HumanDecisionCreate.model_validate(
            {
                "decision": "approve",
                "reasoning": "x" * 4001,
            }
        )


def test_user_feedback_metadata_rejects_oversized_or_deep_json() -> None:
    with pytest.raises(ValidationError):
        UserFeedbackCreate.model_validate(
            {
                "agree": "agree",
                "will_trade": "will_trade",
                "metadata": {"items": list(range(121))},
            }
        )

    with pytest.raises(ValidationError):
        UserFeedbackCreate.model_validate(
            {
                "agree": "agree",
                "will_trade": "will_trade",
                "metadata": {
                    "a": {
                        "b": {
                            "c": {
                                "d": {
                                    "e": {
                                        "f": {
                                            "g": "too deep",
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
            }
        )


def test_user_feedback_reason_is_bounded() -> None:
    with pytest.raises(ValidationError):
        UserFeedbackCreate.model_validate(
            {
                "agree": "disagree",
                "will_trade": "will_not_trade",
                "disagreement_reason": "x" * 4001,
            }
        )


def test_recommendation_payload_bounds_trade_json_fields() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
        "recommended_action": "open",
        "priority_score": 80,
        "portfolio_fit_score": 70,
        "margin_efficiency_score": 75,
        "margin_required": 10_000,
        "reasoning": "test",
        "expires_at": now,
    }

    with pytest.raises(ValidationError):
        RecommendationCreate.model_validate(
            {
                **base_payload,
                "legs": [{"asset": f"RB{index}", "direction": "long"} for index in range(9)],
            }
        )

    with pytest.raises(ValidationError):
        RecommendationCreate.model_validate(
            {
                **base_payload,
                "risk_items": ["x" * 801],
            }
        )

    with pytest.raises(ValidationError):
        RecommendationCreate.model_validate(
            {
                **base_payload,
                "backtest_summary": {"bad": object()},
            }
        )


def test_position_payload_bounds_trade_json_fields() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
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
    }

    with pytest.raises(ValidationError):
        PositionCreate.model_validate(
            {
                **base_payload,
                "legs": [{"asset": f"RU{index}", "direction": "long"} for index in range(9)],
            }
        )

    with pytest.raises(ValidationError):
        PositionCreate.model_validate(
            {
                **base_payload,
                "propagation_nodes": [{"symbol": f"RU{index}"} for index in range(41)],
            }
        )

    with pytest.raises(ValidationError):
        PositionCreate.model_validate(
            {
                **base_payload,
                "legs": [{"asset": "RU", "metadata": {"bad": object()}}],
            }
        )


def test_strategy_payload_bounds_json_and_reference_fields() -> None:
    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "strategy",
                "description": "test",
                "hypothesis": {f"key_{index}": index for index in range(41)},
            }
        )

    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "strategy",
                "description": "test",
                "validation": {"bad": object()},
            }
        )

    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "strategy",
                "description": "test",
                "related_alert_ids": [f"alert-{index}" for index in range(101)],
            }
        )


def test_strategy_payload_bounds_text_fields_and_references() -> None:
    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "x" * 161,
                "description": "test",
            }
        )

    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "strategy",
                "description": "x" * 4001,
            }
        )

    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "strategy",
                "description": "test",
                "recommendation_history": [""],
            }
        )

    with pytest.raises(ValidationError):
        StrategyCreate.model_validate(
            {
                "name": "strategy",
                "description": "test",
                "execution_feedback_ids": ["x" * 81],
            }
        )


def test_market_data_payload_bounds_strings_and_ohlc() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
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
    }

    with pytest.raises(ValidationError):
        MarketDataCreate.model_validate({**base_payload, "symbol": "X" * 33})

    with pytest.raises(ValidationError):
        MarketDataCreate.model_validate({**base_payload, "currency": "CNYY"})

    with pytest.raises(ValidationError):
        MarketDataCreate.model_validate({**base_payload, "high": 3190})

    with pytest.raises(ValidationError):
        MarketDataCreate.model_validate({**base_payload, "volume": -1})


def test_industry_data_payload_bounds_strings_and_value() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
        "symbol": "RB",
        "data_type": "inventory",
        "value": 42,
        "unit": "kt",
        "source": "manual",
        "timestamp": now,
    }

    with pytest.raises(ValidationError):
        IndustryDataCreate.model_validate({**base_payload, "data_type": "x" * 31})

    with pytest.raises(ValidationError):
        IndustryDataCreate.model_validate({**base_payload, "source": "x" * 51})

    with pytest.raises(ValidationError):
        IndustryDataCreate.model_validate({**base_payload, "value": 1_000_000_000_001})


def test_contract_payload_bounds_identifiers_and_liquidity() -> None:
    with pytest.raises(ValidationError):
        ContractCreate.model_validate({"symbol": "X" * 33, "contract_month": "2510"})

    with pytest.raises(ValidationError):
        ContractCreate.model_validate({"symbol": "RB", "contract_month": "x" * 21})

    with pytest.raises(ValidationError):
        ContractCreate.model_validate({"symbol": "RB", "contract_month": "2510", "volume": -1})


def test_news_event_payload_normalizes_affected_symbols() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    payload = NewsEventCreate.model_validate(
        {
            "source": "gdelt",
            "title": "Supply event",
            "published_at": now,
            "event_type": "supply",
            "affected_symbols": [" rb ", "RB", " sc "],
            "direction": "bullish",
            "severity": 3,
            "time_horizon": "short",
            "llm_confidence": 0.7,
        }
    )

    assert payload.affected_symbols == ["RB", "SC"]


def test_news_event_payload_bounds_text_and_symbol_fields() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
        "source": "gdelt",
        "title": "Supply event",
        "published_at": now,
        "event_type": "supply",
        "direction": "bullish",
        "severity": 3,
        "time_horizon": "short",
        "llm_confidence": 0.7,
    }

    with pytest.raises(ValidationError):
        NewsEventCreate.model_validate({**base_payload, "title": "x" * 301})

    with pytest.raises(ValidationError):
        NewsEventCreate.model_validate({**base_payload, "content_text": "x" * 20001})

    with pytest.raises(ValidationError):
        NewsEventCreate.model_validate(
            {
                **base_payload,
                "affected_symbols": [f"S{index}" for index in range(21)],
            }
        )

    with pytest.raises(ValidationError):
        NewsEventCreate.model_validate({**base_payload, "source_count": 51})


def test_news_event_payload_bounds_extraction_payload() -> None:
    now = datetime(2026, 5, 7, tzinfo=timezone.utc)
    base_payload = {
        "source": "gdelt",
        "title": "Supply event",
        "published_at": now,
        "event_type": "supply",
        "direction": "bullish",
        "severity": 3,
        "time_horizon": "short",
        "llm_confidence": 0.7,
    }

    with pytest.raises(ValidationError):
        NewsEventCreate.model_validate(
            {
                **base_payload,
                "extraction_payload": {f"key_{index}": index for index in range(41)},
            }
        )

    with pytest.raises(ValidationError):
        NewsEventCreate.model_validate(
            {
                **base_payload,
                "extraction_payload": {"bad": object()},
            }
        )
