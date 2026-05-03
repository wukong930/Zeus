from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy_runs import StrategyRun
from app.services.backtest.calibration_replay import CURRENT_WARNING, CalibrationStrategy
from app.services.backtest.multiple_testing import deflated_sharpe_ratio


def stable_strategy_hash(
    *,
    strategy_name: str,
    strategy_space: str,
    params: dict[str, Any],
) -> str:
    payload = {
        "strategy_name": strategy_name,
        "strategy_space": strategy_space,
        "params": params,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_strategy_run(
    *,
    strategy_name: str,
    strategy_space: str,
    params: dict[str, Any],
    data_start: datetime,
    data_end: datetime,
    raw_sharpe: float,
    returns_count: int,
    trials: int,
    calibration_strategy: CalibrationStrategy = "pit",
    run_by: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> StrategyRun:
    deflated = deflated_sharpe_ratio(
        raw_sharpe=raw_sharpe,
        returns_count=returns_count,
        trials=trials,
    )
    warning = CURRENT_WARNING if calibration_strategy == "current" else None
    return StrategyRun(
        strategy_hash=stable_strategy_hash(
            strategy_name=strategy_name,
            strategy_space=strategy_space,
            params=params,
        ),
        strategy_name=strategy_name,
        strategy_space=strategy_space,
        params=params,
        data_start=data_start,
        data_end=data_end,
        raw_sharpe=raw_sharpe,
        deflated_sharpe=deflated.deflated_sharpe,
        deflated_pvalue=deflated.deflated_pvalue,
        passed_gate=deflated.passed_gate and calibration_strategy != "current",
        calibration_strategy=calibration_strategy,
        result_warning=warning,
        metrics={
            **(metrics or {}),
            "multiple_testing": deflated.to_dict(),
            "returns_count": returns_count,
            "trials": trials,
        },
        run_by=run_by,
    )


async def record_strategy_run(
    session: AsyncSession,
    **kwargs,
) -> StrategyRun:
    row = build_strategy_run(**kwargs)
    session.add(row)
    await session.flush()
    return row
