import httpx
import pandas as pd

from app.core.config import Settings
from app.services.data_sources.akshare_futures import _rows_from_frame, parse_akshare_symbols
from app.services.data_sources.fred import FredSeries, collect_fred_indicators, row_from_fred_payload
from app.services.data_sources.free_ingest import market_context_payloads
from app.services.data_sources.open_meteo import WeatherLocation, rows_from_weather_payload
from app.services.data_sources.registry import data_source_statuses


def test_parse_akshare_symbols_uses_defaults_when_blank() -> None:
    assert parse_akshare_symbols(" RB0, nr0 ,, ") == ("RB0", "NR0")
    assert parse_akshare_symbols("")[:2] == ("RB0", "HC0")


def test_akshare_rows_from_frame_normalizes_daily_prices() -> None:
    frame = pd.DataFrame(
        [
            {
                "date": "2026-05-01",
                "open": 3200,
                "high": 3300,
                "low": 3190,
                "close": 3280,
                "volume": 1000,
                "hold": 2200,
            }
        ]
    )

    rows = _rows_from_frame(frame, query_symbol="RB0", limit=10)

    assert len(rows) == 1
    assert rows[0].symbol == "RB"
    assert rows[0].contract_month == "main"
    assert rows[0].exchange == "SHFE"
    assert rows[0].close == 3280
    assert rows[0].open_interest == 2200


def test_open_meteo_payload_creates_weather_industry_rows() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)
    rows = rows_from_weather_payload(
        location,
        {
            "daily": {
                "time": ["2026-05-04", "2026-05-05"],
                "precipitation_sum": [12.5, 7.5],
                "temperature_2m_max": [31.0, 33.0],
                "temperature_2m_min": [24.0, 23.5],
            }
        },
    )

    assert {row.data_type for row in rows} == {
        "weather_precip_7d",
        "weather_temp_max_7d",
        "weather_temp_min_7d",
    }
    assert rows[0].symbol == "NR"
    assert rows[0].value == 20.0


def test_fred_payload_skips_missing_values_and_uses_latest_numeric() -> None:
    row = row_from_fred_payload(
        FredSeries("DCOILWTICO", "SC", "macro_wti_usd_bbl", "USD/bbl"),
        {
            "observations": [
                {"date": "2026-05-03", "value": "."},
                {"date": "2026-05-02", "value": "65.12"},
            ]
        },
    )

    assert row is not None
    assert row.symbol == "SC"
    assert row.value == 65.12
    assert row.source_key == "fred:DCOILWTICO:2026-05-02"


async def test_fred_collector_uses_keyed_observation_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fred/series/observations"
        assert request.url.params["api_key"] == "fred-test"
        assert request.url.params["series_id"] == "DGS10"
        return httpx.Response(
            200,
            json={"observations": [{"date": "2026-05-01", "value": "4.21"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await collect_fred_indicators(
            api_key="fred-test",
            base_url="https://fred.test/fred",
            series=(FredSeries("DGS10", "MACRO", "macro_us10y_yield", "pct"),),
            client=client,
        )

    assert len(rows) == 1
    assert rows[0].data_type == "macro_us10y_yield"


def test_market_context_payloads_group_rows_by_symbol() -> None:
    rows = _rows_from_frame(
        pd.DataFrame(
            [
                {"date": "2026-05-01", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
                {"date": "2026-05-02", "open": 2, "high": 3, "low": 2, "close": 3, "volume": 11},
            ]
        ),
        query_symbol="SC0",
        limit=10,
    )

    contexts = market_context_payloads(rows)

    assert len(contexts) == 1
    assert contexts[0]["symbol1"] == "SC"
    assert contexts[0]["category"] == "energy"
    assert len(contexts[0]["market_data"]) == 2


def test_data_source_registry_marks_keyed_sources() -> None:
    settings = Settings(
        data_source_fred_enabled=True,
        fred_api_key="fred-test",
        data_source_eia_enabled=True,
        eia_api_key="",
        _env_file=None,
    )

    statuses = {status.id: status for status in data_source_statuses(settings)}

    assert statuses["fred"].status == "ready"
    assert statuses["eia"].status == "missing_key"
    assert statuses["open_meteo"].free_tier == "free_no_key"
