from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core.events import ZeusEvent
from app.main import create_app
from app.services.llm.types import LLMCompletionResult
from app.services.pipeline.handlers import handle_scenario_requested
from app.services.scenarios import (
    ScenarioRequest,
    run_scenario_simulation,
    run_scenario_simulation_with_llm_narrative,
    run_what_if,
)
from app.services.scenarios.monte_carlo import run_monte_carlo
from app.services.scenarios.what_if import impact_for_symbol


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


def test_what_if_propagates_natural_rubber_shock_to_ru() -> None:
    result = run_what_if({"NR": 0.10}, max_depth=3)

    ru_impact = impact_for_symbol(result, "RU")

    assert ru_impact is not None
    assert ru_impact.propagated_shock == 0.0804
    assert ru_impact.dominant_driver == "NR"
    assert result.key_paths[0].root_symbol == "NR"
    assert result.key_paths[0].target_symbol == "RU"


def test_monte_carlo_is_deterministic_and_orders_percentiles() -> None:
    first = run_monte_carlo(
        target_symbol="RU",
        base_price=100.0,
        days=15,
        simulations=500,
        volatility_pct=0.012,
        applied_shock=0.04,
        seed=42,
    )
    second = run_monte_carlo(
        target_symbol="RU",
        base_price=100.0,
        days=15,
        simulations=500,
        volatility_pct=0.012,
        applied_shock=0.04,
        seed=42,
    )

    assert first.terminal_distribution == second.terminal_distribution
    assert first.terminal_distribution["p95"] > first.terminal_distribution["p50"]
    assert first.terminal_distribution["p50"] > first.terminal_distribution["p5"]
    assert first.downside_probability < 0.5


def test_simulator_combines_what_if_and_monte_carlo_report() -> None:
    report = run_scenario_simulation(
        ScenarioRequest(
            target_symbol="RU2509",
            shocks={"NR": 0.06},
            base_price=15400,
            days=20,
            simulations=500,
            seed=11,
        )
    )

    payload = report.to_dict()
    assert payload["target_symbol"] == "RU"
    assert payload["monte_carlo"]["applied_shock"] == 0.04824
    assert payload["monte_carlo"]["terminal_distribution"]["p50"] > 15400
    assert "NR" in payload["narrative"]
    assert payload["risk_points"]
    assert payload["suggested_actions"]
    assert payload["narrative_source"] == "deterministic"


async def test_llm_narrative_enrichment_updates_report_text() -> None:
    async def fake_completer(**_kwargs):
        return LLMCompletionResult(
            content=json.dumps(
                {
                    "narrative": "LLM narrative: NR pass-through keeps RU skewed upward.",
                    "risk_points": ["NR path is the dominant driver."],
                    "suggested_actions": ["Keep the scenario under active review."],
                }
            ),
            model="fake-llm",
        )

    report = await run_scenario_simulation_with_llm_narrative(
        ScenarioRequest(
            target_symbol="RU",
            shocks={"NR": 0.06},
            base_price=15400,
            simulations=500,
        ),
        completer=fake_completer,
    )

    payload = report.to_dict()
    assert payload["narrative_source"] == "llm"
    assert payload["narrative"].startswith("LLM narrative")
    assert payload["risk_points"] == ["NR path is the dominant driver."]


async def test_llm_narrative_enrichment_falls_back_on_error() -> None:
    async def failing_completer(**_kwargs):
        raise RuntimeError("llm unavailable")

    report = await run_scenario_simulation_with_llm_narrative(
        ScenarioRequest(target_symbol="RU", shocks={"NR": 0.06}, simulations=500),
        completer=failing_completer,
    )

    assert report.narrative_source == "deterministic_fallback"
    assert "RU 场景推演显示" in report.narrative


def test_scenario_simulation_api_returns_report() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/scenarios/simulate",
        json={
            "target_symbol": "RB",
            "base_price": 3250,
            "shocks": {"I": 0.10, "J": -0.05},
            "days": 20,
            "simulations": 500,
            "volatility_pct": 0.018,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target_symbol"] == "RB"
    assert payload["what_if"]["impacts"]
    assert payload["monte_carlo"]["terminal_distribution"]["p95"] > payload["monte_carlo"][
        "terminal_distribution"
    ]["p5"]


async def test_scenario_requested_handler_publishes_completed_event() -> None:
    event = ZeusEvent(
        channel="scenario.requested",
        payload={
            "request": {
                "target_symbol": "RU",
                "base_price": 15400,
                "shocks": {"NR": 0.06},
                "days": 20,
                "simulations": 500,
                "seed": 11,
            }
        },
        source="test",
    )
    publisher = CapturingPublisher()

    completed = await handle_scenario_requested(event, publisher=publisher)

    assert completed is not None
    assert completed.channel == "scenario.completed"
    assert publisher.calls[0]["event"].payload["report"]["target_symbol"] == "RU"
    assert publisher.calls[0]["kwargs"]["source"] == "scenario-simulator"
