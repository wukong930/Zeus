"""CLI: generate the governed cross-sectional reversal forecast as-of a date.

Produces a deterministic, reproducible ForecastRecord (dollar-neutral target
weights + feature_hash) and persists it as an advisory / shadow signal
(decision_grade=False). It does NOT make a production trading decision — that
requires governance promotion.

Usage (from backend/):
    .venv/bin/python -m app.tools.run_forecast
    .venv/bin/python -m app.tools.run_forecast --as-of 2026-05-28 --k 10 --no-persist
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.services.prediction.cross_sectional import (
    DEFAULT_K,
    DEFAULT_LOOKBACK,
    generate_cross_sectional_forecast,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the governed XS reversal forecast")
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD; default = now")
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--no-persist", action="store_true", help="compute only, do not write")
    args = parser.parse_args()

    if args.as_of:
        as_of = datetime.fromisoformat(args.as_of).replace(tzinfo=timezone.utc)
    else:
        as_of = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as session:
        row = await generate_cross_sectional_forecast(
            session,
            as_of=as_of,
            lookback=args.lookback,
            k=args.k,
            persist=not args.no_persist,
        )
        if not args.no_persist:
            await session.commit()

    print(
        f"forecast {row.signal} ({row.model_version})  as_of {row.as_of.date()}  "
        f"universe {row.universe_size}  decision_grade={row.decision_grade}"
    )
    print(f"feature_hash {row.feature_hash[:16]}...  ({'persisted' if not args.no_persist else 'not persisted'})")
    if not row.target_weights:
        print("(insufficient universe for a position)")
        return
    print("target weights — LONG losers (+) / SHORT winners (-):")
    for symbol, weight in sorted(row.target_weights.items(), key=lambda item: item[1]):
        print(f"   {symbol:<6} {weight:+.3f}")
    print(
        "\nadvisory / shadow only — must pass governance review + shadow validation before "
        "anything treats it as authoritative."
    )


if __name__ == "__main__":
    asyncio.run(main())
