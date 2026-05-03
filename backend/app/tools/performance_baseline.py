import asyncio
import json
from datetime import datetime, timedelta, timezone
from statistics import mean
from time import perf_counter

from sqlalchemy import delete

from app.core.database import AsyncSessionLocal
from app.models.market_data import MarketData
from app.schemas.common import MarketDataCreate
from app.services.etl.writers import append_market_data
from app.services.market_data.pit import get_market_data_pit
from app.services.signals.detector import SignalDetector
from app.services.signals.types import IndustryPoint, MarketBar, SpreadStatistics, TriggerContext


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * pct)))
    return ordered[idx]


def summarize(durations: list[float], *, iterations: int) -> dict[str, float | int]:
    return {
        "iterations": iterations,
        "mean_ms": round(mean(durations) * 1000, 3),
        "p95_ms": round(percentile(durations, 0.95) * 1000, 3),
        "max_ms": round(max(durations) * 1000, 3),
    }


async def measure_signal_detector(iterations: int = 200) -> dict:
    detector = SignalDetector()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    closes = [100 + idx * 0.15 for idx in range(30)] + [106, 98, 112, 94, 119, 90, 126]
    market_data = [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=close,
            high=close + 1.5,
            low=close - 1.5,
            close=close,
            volume=500 if idx == len(closes) - 1 else 120 + idx,
        )
        for idx, close in enumerate(closes)
    ]
    inventory = [
        IndustryPoint(value=value, timestamp=start + timedelta(days=idx))
        for idx, value in enumerate([100, 101, 99, 100, 98, 130, 132, 135])
    ]
    context = TriggerContext(
        symbol1="RB",
        symbol2="HC",
        category="ferrous",
        timestamp=datetime.now(timezone.utc),
        market_data=market_data,
        inventory=inventory,
        spread_stats=SpreadStatistics(
            adf_p_value=0.03,
            half_life=12,
            spread_mean=10,
            spread_std_dev=2,
            current_z_score=2.8,
        ),
    )

    durations: list[float] = []
    result_count = 0
    for _ in range(iterations):
        started = perf_counter()
        results = await detector.detect(context)
        durations.append(perf_counter() - started)
        result_count = len(results)

    return {**summarize(durations, iterations=iterations), "result_count": result_count}


async def measure_pit_queries(iterations: int = 100, rows: int = 250) -> dict:
    symbol = "ZZPERF"
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    vintage_old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    vintage_new = datetime(2026, 1, 2, tzinfo=timezone.utc)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(MarketData).where(MarketData.symbol == symbol))
        await session.commit()

        old_rows = [
            _market_payload(symbol=symbol, timestamp=start + timedelta(days=idx), close=100 + idx * 0.1)
            for idx in range(rows)
        ]
        new_rows = [
            _market_payload(symbol=symbol, timestamp=start + timedelta(days=idx), close=101 + idx * 0.1)
            for idx in range(rows)
        ]
        await append_market_data(session, old_rows, vintage_at=vintage_old)
        await append_market_data(session, new_rows, vintage_at=vintage_new)
        await session.commit()

        latest_durations: list[float] = []
        as_of_durations: list[float] = []
        as_of = vintage_old + timedelta(seconds=1)

        for _ in range(iterations):
            started = perf_counter()
            await get_market_data_pit(session, symbol=symbol, limit=rows)
            latest_durations.append(perf_counter() - started)

            started = perf_counter()
            await get_market_data_pit(session, symbol=symbol, as_of=as_of, limit=rows)
            as_of_durations.append(perf_counter() - started)

        await session.execute(delete(MarketData).where(MarketData.symbol == symbol))
        await session.commit()

    return {
        "rows_per_vintage": rows,
        "vintages": 2,
        "latest": summarize(latest_durations, iterations=iterations),
        "as_of": summarize(as_of_durations, iterations=iterations),
    }


def _market_payload(symbol: str, timestamp: datetime, close: float) -> MarketDataCreate:
    return MarketDataCreate(
        market="CN",
        exchange="SHFE",
        commodity="perf",
        symbol=symbol,
        contract_month="2505",
        timestamp=timestamp,
        open=close - 0.5,
        high=close + 1,
        low=close - 1,
        close=close,
        settle=close,
        volume=1000,
        open_interest=5000,
    )


async def main() -> None:
    signal = await measure_signal_detector()
    pit = await measure_pit_queries()
    print(
        json.dumps(
            {
                "signal_detector": signal,
                "pit_query": pit,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
