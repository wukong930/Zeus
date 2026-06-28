"""CLI: backfill long AKShare daily history into market_data for replay.

Idempotent (skips ``akshare_hist:`` rows already present) and point-in-time
correct (``vintage_at`` = each bar's own date). Run with --dry-run first to see
what would be loaded without writing.

Usage (from backend/):
    .venv/bin/python -m app.tools.backfill_akshare_history --dry-run
    .venv/bin/python -m app.tools.backfill_akshare_history --start 20100101
    .venv/bin/python -m app.tools.backfill_akshare_history --symbols RB0,CU0,I0
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.market_data import MarketData
from app.services.data_sources.akshare_futures import parse_akshare_symbols
from app.services.data_sources.akshare_history import (
    DEFAULT_HISTORY_START,
    HISTORY_SOURCE_PREFIX,
    collect_akshare_history,
)
from app.services.etl.writers import append_market_data

INSERT_CHUNK = 2000


async def _existing_history_keys(session) -> set[str]:
    result = await session.scalars(
        select(MarketData.source_key).where(
            MarketData.source_key.like(f"{HISTORY_SOURCE_PREFIX}:%")
        )
    )
    return {key for key in result.all() if key}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill long AKShare daily history for replay")
    parser.add_argument("--symbols", default=None, help="comma-separated; default = built-in set")
    parser.add_argument("--start", default=DEFAULT_HISTORY_START, help="YYYYMMDD")
    parser.add_argument("--end", default=None, help="YYYYMMDD; default = today")
    parser.add_argument("--dry-run", action="store_true", help="fetch + report, write nothing")
    args = parser.parse_args()

    symbols = parse_akshare_symbols(args.symbols)
    end = args.end or datetime.now(timezone.utc).strftime("%Y%m%d")

    print(f"fetching {len(symbols)} symbols, {args.start} → {end} ...")
    result = await collect_akshare_history(symbols=symbols, start_date=args.start, end_date=end)
    rows = result.rows

    days = sorted({row.timestamp.date() for row in rows})
    syms = sorted({row.symbol for row in rows})
    print(f"fetched rows: {len(rows)}  symbols: {len(syms)}  errors: {len(result.errors)}")
    if days:
        print(f"date range: {days[0]} → {days[-1]}  ({len(days)} trading days)")
    for err in result.errors[:10]:
        print(f"  ERROR {err['source']}: {err['error'][:120]}")

    if args.dry_run:
        print("dry-run: nothing written.")
        return

    async with AsyncSessionLocal() as session:
        existing = await _existing_history_keys(session)
        fresh = [row for row in rows if row.source_key not in existing]
        print(f"already present: {len(rows) - len(fresh)}  to insert: {len(fresh)}")

        written = 0
        for start in range(0, len(fresh), INSERT_CHUNK):
            chunk = fresh[start : start + INSERT_CHUNK]
            await append_market_data(session, chunk)
            await session.commit()
            written += len(chunk)
            print(f"  inserted {written}/{len(fresh)}")
    print(f"done. inserted {written} rows.")


if __name__ == "__main__":
    asyncio.run(main())
