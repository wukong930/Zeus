from datetime import datetime, timezone

from app.schemas.common import IndustryDataCreate, MarketDataCreate
from app.services.etl.writers import (
    industry_source_key,
    market_source_key,
    prepare_industry_data_rows,
    prepare_market_data_rows,
)


def test_market_source_key_is_stable_and_utc_normalized() -> None:
    timestamp = datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc)

    assert market_source_key("RB", "main", timestamp) == "RB:main:2026-05-03T09:00:00Z"


def test_prepare_market_data_rows_adds_append_only_metadata() -> None:
    timestamp = datetime(2026, 5, 3, tzinfo=timezone.utc)
    vintage = datetime(2026, 5, 4, tzinfo=timezone.utc)

    rows = prepare_market_data_rows(
        [
            MarketDataCreate(
                market="SHFE",
                exchange="SHFE",
                commodity="螺纹钢",
                symbol="RB",
                contract_month="main",
                timestamp=timestamp,
                open=3600,
                high=3660,
                low=3580,
                close=3640,
                settle=3640,
                volume=1000,
                open_interest=2000,
            )
        ],
        vintage_at=vintage,
    )

    assert rows[0].source_key == "RB:main:2026-05-03T00:00:00Z"
    assert rows[0].vintage_at == vintage


def test_prepare_industry_data_rows_adds_append_only_metadata() -> None:
    timestamp = datetime(2026, 5, 3, tzinfo=timezone.utc)
    vintage = datetime(2026, 5, 4, tzinfo=timezone.utc)

    rows = prepare_industry_data_rows(
        [
            IndustryDataCreate(
                symbol="RB",
                data_type="inventory",
                value=432.5,
                unit="万吨",
                source="manual",
                timestamp=timestamp,
            )
        ],
        vintage_at=vintage,
    )

    assert industry_source_key("RB", "inventory", timestamp) == "RB:inventory:2026-05-03T00:00:00Z"
    assert rows[0].source_key == "RB:inventory:2026-05-03T00:00:00Z"
    assert rows[0].vintage_at == vintage
