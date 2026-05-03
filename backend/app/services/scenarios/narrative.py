from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.llm.registry import complete_with_llm_controls
from app.services.llm.types import LLMCompletionOptions, LLMCompletionResult, LLMMessage
from app.services.scenarios.types import ScenarioReport

ScenarioCompleter = Callable[..., Awaitable[LLMCompletionResult]]


class ScenarioNarrativeResult(BaseModel):
    narrative: str = Field(min_length=20)
    risk_points: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


async def enrich_report_with_llm_narrative(
    report: ScenarioReport,
    *,
    session: AsyncSession | None = None,
    completer: ScenarioCompleter = complete_with_llm_controls,
) -> ScenarioReport:
    try:
        result = await completer(
            module="scenario_simulator",
            session=session,
            options=LLMCompletionOptions(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "You are Zeus Scenario Simulator. Return strict JSON with "
                            "narrative, risk_points, and suggested_actions. Keep the analysis "
                            "concise, grounded in the provided numeric distribution, and do not "
                            "invent external market data."
                        ),
                    ),
                    LLMMessage(role="user", content=json.dumps(_llm_payload(report), ensure_ascii=False)),
                ],
                temperature=0,
                max_tokens=900,
                json_mode=True,
                json_schema=ScenarioNarrativeResult.model_json_schema(),
            ),
        )
        parsed = ScenarioNarrativeResult.model_validate_json(result.content)
    except (Exception, ValidationError):
        return replace(report, narrative_source="deterministic_fallback")

    return replace(
        report,
        narrative=parsed.narrative,
        risk_points=tuple(parsed.risk_points[:6] or report.risk_points),
        suggested_actions=tuple(parsed.suggested_actions[:4] or report.suggested_actions),
        narrative_source="llm",
    )


def _llm_payload(report: ScenarioReport) -> dict[str, Any]:
    payload = report.to_dict()
    monte_carlo = payload["monte_carlo"]
    what_if = payload["what_if"]
    return {
        "target_symbol": payload["target_symbol"],
        "base_price": payload["base_price"],
        "shocks": what_if["shocks"],
        "target_impact": next(
            (
                impact
                for impact in what_if["impacts"]
                if impact["symbol"] == payload["target_symbol"]
            ),
            None,
        ),
        "key_paths": what_if["key_paths"][:5],
        "terminal_distribution": monte_carlo["terminal_distribution"],
        "expected_return": monte_carlo["expected_return"],
        "downside_probability": monte_carlo["downside_probability"],
        "deterministic_narrative": payload["narrative"],
        "risk_points": payload["risk_points"],
        "suggested_actions": payload["suggested_actions"],
    }
