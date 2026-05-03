from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import rollback_if_possible
from app.models.llm_cache import LLMBudget


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    near_limit: bool
    module: str
    current_spend_usd: float
    monthly_budget_usd: float | None
    reason: str = "ok"


async def check_llm_budget(
    session: AsyncSession | None,
    *,
    module: str,
    as_of: datetime | None = None,
) -> BudgetDecision:
    if session is None:
        return BudgetDecision(True, False, module, 0.0, None, "no_session")
    effective_at = as_of or datetime.now(timezone.utc)
    start, _ = month_bounds(effective_at.date())
    try:
        row = (
            await session.scalars(
                select(LLMBudget)
                .where(
                    LLMBudget.module == module,
                    LLMBudget.period_start == start,
                    LLMBudget.status == "active",
                )
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        return BudgetDecision(True, False, module, 0.0, None, "budget_lookup_failed")
    if row is None:
        return BudgetDecision(True, False, module, 0.0, None, "no_budget")
    if row.current_spend_usd >= row.monthly_budget_usd:
        return BudgetDecision(
            False,
            True,
            module,
            row.current_spend_usd,
            row.monthly_budget_usd,
            "budget_exhausted",
        )
    near_limit = row.current_spend_usd >= row.monthly_budget_usd * row.alert_threshold
    return BudgetDecision(
        True,
        near_limit,
        module,
        row.current_spend_usd,
        row.monthly_budget_usd,
        "near_limit" if near_limit else "ok",
    )


async def add_budget_spend(
    session: AsyncSession | None,
    *,
    module: str,
    amount_usd: float,
    as_of: datetime | None = None,
) -> None:
    if session is None or amount_usd <= 0:
        return
    effective_at = as_of or datetime.now(timezone.utc)
    start, _ = month_bounds(effective_at.date())
    try:
        row = (
            await session.scalars(
                select(LLMBudget)
                .where(
                    LLMBudget.module == module,
                    LLMBudget.period_start == start,
                    LLMBudget.status == "active",
                )
                .limit(1)
            )
        ).first()
    except Exception:
        await rollback_if_possible(session)
        return
    if row is None:
        return
    row.current_spend_usd = float(row.current_spend_usd or 0) + amount_usd
    row.updated_at = effective_at
    await session.flush()


def month_bounds(value: date) -> tuple[date, date]:
    start = value.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end
