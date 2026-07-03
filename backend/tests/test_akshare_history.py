from datetime import date

import pandas as pd

from app.services.data_sources.akshare_history import (
    collect_akshare_history,
    history_rows_from_frame,
    history_source_key,
)

_COLUMNS = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "持仓量", "动态结算价"]


def _frame(rows: list[list]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=_COLUMNS)


def test_history_rows_are_point_in_time_and_use_hist_source_key():
    frame = _frame(
        [
            ["2015-03-10", 100, 110, 95, 105, 1000, 5000, 104],
            ["2015-03-11", 105, 108, 101, 103, 800, 5100, 103],
        ]
    )
    rows = history_rows_from_frame(frame, query_symbol="RB0")

    assert len(rows) == 2
    first = rows[0]
    assert first.symbol == "RB"
    assert first.contract_month == "main"
    assert first.exchange == "SHFE"
    assert first.close == 105
    assert first.settle == 104  # captured from the 动态结算价 column
    # vintage_at = the bar's own date, so a replay as_of that day can see it
    assert first.vintage_at is not None
    assert first.vintage_at.date() == date(2015, 3, 10)
    assert first.source_key == history_source_key("RB0", "2015-03-10")
    assert first.source_key.startswith("akshare_hist:")


def test_history_clamps_bad_ohlc_and_skips_unparseable_rows():
    frame = _frame(
        [
            ["2015-03-10", 100, 90, 95, 105, 1000, 5000, 104],  # high < close -> clamp
            ["bad-date", 100, 110, 95, 105, 1000, 5000, 104],  # unparseable date -> skip
            ["2015-03-12", 100, 110, 95, None, 1000, 5000, 104],  # missing close -> skip
        ]
    )
    rows = history_rows_from_frame(frame, query_symbol="CU0")

    assert len(rows) == 1
    only = rows[0]
    assert only.close == 105
    assert only.high >= max(only.open, only.low, only.close)  # clamped to a valid bar


def test_empty_frame_yields_no_rows():
    assert history_rows_from_frame(_frame([]), query_symbol="RB0") == []


async def test_collect_aggregates_rows_and_records_per_symbol_errors():
    frames = {"RB0": _frame([["2015-03-10", 100, 110, 95, 105, 1000, 5000, 104]])}

    def fake_fetch(symbol: str, start_date: str, end_date: str):
        if symbol == "BOOM0":
            raise RuntimeError("network down")
        return frames.get(symbol, _frame([]))

    result = await collect_akshare_history(
        symbols=["RB0", "BOOM0"],
        start_date="20150101",
        end_date="20150201",
        fetcher=fake_fetch,
    )

    assert len(result.rows) == 1
    assert result.rows[0].symbol == "RB"
    assert len(result.errors) == 1
    assert "BOOM0" in result.errors[0]["source"]
