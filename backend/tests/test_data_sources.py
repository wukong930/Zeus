import json

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.data_sources.akshare_futures import (
    _rows_from_frame,
    collect_akshare_market_data,
    parse_akshare_symbols,
)
from app.services.data_sources.accuweather import (
    collect_accuweather_current_conditions,
    rows_from_current_conditions_payload,
)
from app.services.data_sources.eia import EiaSeries, collect_eia_indicators, row_from_eia_payload
from app.services.data_sources.fred import FredSeries, collect_fred_indicators, row_from_fred_payload
from app.services.data_sources.free_ingest import (
    market_context_payloads,
    run_free_data_ingest,
    safe_error_message,
)
from app.services.data_sources.nasa_power import (
    baseline_rows_from_power_payload,
    collect_nasa_power_weather_baselines,
    collect_nasa_power_weather,
    rows_from_power_payload,
)
from app.services.data_sources.open_meteo import WeatherLocation, rows_from_weather_payload
from app.services.data_sources.registry import data_source_statuses
from app.services.data_sources.types import DataSourceStatus
from app.services.data_sources.tushare_futures import (
    collect_tushare_market_data,
    dedupe_active_contracts,
    parse_csv_tuple,
    rows_from_tushare_payload,
)


def test_parse_akshare_symbols_uses_defaults_when_blank() -> None:
    assert parse_akshare_symbols(" RB0, nr0, RB0 ,, ") == ("RB0", "NR0")
    assert parse_akshare_symbols("")[:2] == ("RB0", "HC0")


def test_parse_akshare_symbols_rejects_unbounded_settings() -> None:
    with pytest.raises(ValueError, match="at most 50"):
        parse_akshare_symbols(",".join(f"RB{i}" for i in range(51)))

    with pytest.raises(ValueError, match="at most 32"):
        parse_akshare_symbols("R" * 33)


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


def test_akshare_rows_reject_missing_required_columns() -> None:
    with pytest.raises(RuntimeError, match="close"):
        _rows_from_frame(
            pd.DataFrame([{"date": "2026-05-01", "price": 3280}]),
            query_symbol="RB0",
            limit=10,
        )


async def test_akshare_collector_records_field_drift_error() -> None:
    def fetcher(_query_symbol: str) -> pd.DataFrame:
        return pd.DataFrame([{"date": "2026-05-01", "price": 3280}])

    result = await collect_akshare_market_data(symbols=("RB0",), fetcher=fetcher)

    assert result.rows == []
    assert result.errors[0]["source"] == "akshare:RB0"
    assert "close" in result.errors[0]["error"]


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


def test_open_meteo_payload_rejects_missing_daily_shape() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)

    with pytest.raises(RuntimeError, match="daily data"):
        rows_from_weather_payload(location, {"hourly": {}})


def test_open_meteo_payload_rejects_missing_required_daily_field() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)

    with pytest.raises(RuntimeError, match="temperature_2m_min"):
        rows_from_weather_payload(
            location,
            {
                "daily": {
                    "time": ["2026-05-04"],
                    "precipitation_sum": [12.5],
                    "temperature_2m_max": [31.0],
                }
            },
        )


def test_open_meteo_payload_rejects_non_list_daily_field() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)

    with pytest.raises(RuntimeError, match="precipitation_sum"):
        rows_from_weather_payload(
            location,
            {
                "daily": {
                    "time": ["2026-05-04"],
                    "precipitation_sum": "12.5",
                    "temperature_2m_max": [31.0],
                    "temperature_2m_min": [24.0],
                }
            },
        )


def test_nasa_power_payload_creates_weather_industry_rows() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)
    rows = rows_from_power_payload(
        location,
        {
            "properties": {
                "parameter": {
                    "PRECTOTCORR": {"20260501": 8.0, "20260502": 4.5},
                    "T2M_MAX": {"20260501": 31.0, "20260502": 33.0},
                    "T2M_MIN": {"20260501": 24.0, "20260502": 23.0},
                }
            }
        },
    )

    assert {row.data_type for row in rows} == {
        "weather_precip_7d",
        "weather_temp_max_7d",
        "weather_temp_min_7d",
    }
    assert rows[0].source == "nasa_power:hat_yai"
    assert rows[0].value == 12.5
    assert rows[0].timestamp.date().isoformat() == "2026-05-02"


def test_nasa_power_payload_rejects_missing_parameter_shape() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)

    with pytest.raises(RuntimeError, match="properties.parameter"):
        rows_from_power_payload(location, {"properties": {"parameters": {}}})


def test_nasa_power_payload_creates_weather_baseline_rows() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)
    rows = baseline_rows_from_power_payload(
        location,
        {
            "properties": {
                "parameter": {
                    "PRECTOTCORR": {
                        "20260501": 8.0,
                        "20260502": 10.0,
                        "20250501": 3.0,
                        "20250502": 4.0,
                        "20240501": 5.0,
                        "20240502": 6.0,
                    },
                    "T2M_MAX": {
                        "20260501": 38.0,
                        "20260502": 40.0,
                        "20250501": 30.0,
                        "20250502": 32.0,
                        "20240501": 34.0,
                        "20240502": 36.0,
                    },
                    "T2M_MIN": {
                        "20260501": 28.0,
                        "20260502": 30.0,
                        "20250501": 20.0,
                        "20250502": 22.0,
                        "20240501": 24.0,
                        "20240502": 26.0,
                    },
                }
            }
        },
        target_end=pd.Timestamp("2026-05-02").date(),
        windows=(
            (pd.Timestamp("2024-05-01").date(), pd.Timestamp("2024-05-02").date()),
            (pd.Timestamp("2025-05-01").date(), pd.Timestamp("2025-05-02").date()),
        ),
        window_days=2,
    )

    assert {row.data_type for row in rows} == {
        "weather_baseline_precip_7d",
        "weather_baseline_temp_mean_7d",
        "weather_precip_pctile_7d",
        "weather_temp_pctile_7d",
    }
    assert rows[0].value == 9.0
    assert rows[1].value == 28.0
    assert rows[2].value == 100.0
    assert rows[3].value == 100.0
    assert rows[0].source == "nasa_power_baseline:hat_yai"


async def test_nasa_power_collector_uses_daily_point_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/temporal/daily/point"
        assert request.url.params["community"] == "AG"
        assert request.url.params["parameters"] == "PRECTOTCORR,T2M_MAX,T2M_MIN"
        assert request.url.params["start"] == "20260501"
        assert request.url.params["end"] == "20260502"
        return httpx.Response(
            200,
            json={
                "properties": {
                    "parameter": {
                        "PRECTOTCORR": {"20260501": 1.0, "20260502": 2.0},
                        "T2M_MAX": {"20260501": 30.0, "20260502": 31.0},
                        "T2M_MIN": {"20260501": 20.0, "20260502": 21.0},
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await collect_nasa_power_weather(
            locations=(WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0),),
            start=pd.Timestamp("2026-05-01").date(),
            end=pd.Timestamp("2026-05-02").date(),
            base_url="https://power.test/api/temporal/daily/point",
            client=client,
        )

    assert len(rows) == 3
    assert rows[0].source_key == "nasa_power:hat_yai:precip:20260501-20260502"


async def test_nasa_power_baseline_collector_uses_historical_window() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/temporal/daily/point"
        assert request.url.params["start"] == "20240501"
        assert request.url.params["end"] == "20260502"
        return httpx.Response(
            200,
            json={
                "properties": {
                    "parameter": {
                        "PRECTOTCORR": {
                            "20240501": 5.0,
                            "20240502": 6.0,
                            "20250501": 3.0,
                            "20250502": 4.0,
                            "20260501": 8.0,
                            "20260502": 10.0,
                        },
                        "T2M_MAX": {
                            "20240501": 34.0,
                            "20240502": 36.0,
                            "20250501": 30.0,
                            "20250502": 32.0,
                            "20260501": 38.0,
                            "20260502": 40.0,
                        },
                        "T2M_MIN": {
                            "20240501": 24.0,
                            "20240502": 26.0,
                            "20250501": 20.0,
                            "20250502": 22.0,
                            "20260501": 28.0,
                            "20260502": 30.0,
                        },
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await collect_nasa_power_weather_baselines(
            locations=(WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0),),
            end=pd.Timestamp("2026-05-02").date(),
            years=2,
            window_days=2,
            base_url="https://power.test/api/temporal/daily/point",
            client=client,
        )

    assert len(rows) == 4
    assert rows[0].source_key == "nasa_power:hat_yai:baseline_precip:2024-2025:0502:2d"
    assert rows[2].data_type == "weather_precip_pctile_7d"


def test_accuweather_current_conditions_payload_creates_rows() -> None:
    location = WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0)
    rows = rows_from_current_conditions_payload(
        location,
        [
            {
                "LocalObservationDateTime": "2026-05-09T12:00:00+07:00",
                "Temperature": {"Metric": {"Value": 31.5}},
                "Precip1hr": {"Metric": {"Value": 2.4}},
                "RelativeHumidity": 83,
                "Wind": {"Speed": {"Metric": {"Value": 18.0}}},
            }
        ],
    )

    assert {row.data_type for row in rows} == {
        "weather_temp_current_c",
        "weather_precip_1h",
        "weather_humidity_pct",
        "weather_wind_kph",
    }
    assert rows[0].source == "accuweather:hat_yai"


async def test_accuweather_collector_uses_geoposition_and_current_conditions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer accuweather-test"
        if request.url.path == "/locations/v1/cities/geoposition/search":
            assert request.url.params["q"] == "7.0,100.0"
            return httpx.Response(200, json={"Key": "12345"})
        if request.url.path == "/currentconditions/v1/12345":
            return httpx.Response(
                200,
                json=[
                    {
                        "LocalObservationDateTime": "2026-05-09T12:00:00+07:00",
                        "Temperature": {"Metric": {"Value": 31.5}},
                    }
                ],
            )
        raise AssertionError(f"unexpected path {request.url.path}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await collect_accuweather_current_conditions(
            api_key="accuweather-test",
            locations=(WeatherLocation("hat_yai", "Hat Yai", "NR", 7.0, 100.0),),
            base_url="https://accuweather.test",
            client=client,
        )

    assert len(rows) == 1
    assert rows[0].data_type == "weather_temp_current_c"


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


def test_fred_payload_rejects_missing_observation_shape() -> None:
    with pytest.raises(RuntimeError, match="observations"):
        row_from_fred_payload(
            FredSeries("DCOILWTICO", "SC", "macro_wti_usd_bbl", "USD/bbl"),
            {"series_id": "DCOILWTICO"},
        )


def test_fred_payload_rejects_observation_field_drift() -> None:
    with pytest.raises(RuntimeError, match="date/value"):
        row_from_fred_payload(
            FredSeries("DCOILWTICO", "SC", "macro_wti_usd_bbl", "USD/bbl"),
            {"observations": [{"period": "2026-05-02", "close": "65.12"}]},
        )


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


def test_eia_payload_uses_latest_weekly_value() -> None:
    row = row_from_eia_payload(
        EiaSeries("petroleum/stoc/wstk", "WCESTUS1", "SC", "eia_crude_stocks_ex_spr", "MBBL"),
        {
            "response": {
                "data": [
                    {
                        "period": "2026-04-24",
                        "series": "WCESTUS1",
                        "value": "459495",
                        "units": "MBBL",
                    }
                ]
            }
        },
    )

    assert row is not None
    assert row.source == "eia"
    assert row.data_type == "eia_crude_stocks_ex_spr"
    assert row.value == 459495
    assert row.source_key == "eia:WCESTUS1:2026-04-24"


def test_eia_payload_rejects_missing_data_shape() -> None:
    with pytest.raises(RuntimeError, match="response\\.data"):
        row_from_eia_payload(
            EiaSeries("petroleum/stoc/wstk", "WCESTUS1", "SC", "eia_crude_stocks_ex_spr", "MBBL"),
            {"request": {"command": "series"}},
        )


def test_eia_payload_rejects_data_field_drift() -> None:
    with pytest.raises(RuntimeError, match="period/series/value"):
        row_from_eia_payload(
            EiaSeries("petroleum/stoc/wstk", "WCESTUS1", "SC", "eia_crude_stocks_ex_spr", "MBBL"),
            {"response": {"data": [{"date": "2026-04-24", "amount": "459495"}]}},
        )


async def test_eia_collector_uses_v2_series_facet_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/petroleum/stoc/wstk/data/"
        assert request.url.params["api_key"] == "eia-test"
        assert request.url.params["facets[series][]"] == "WGTSTUS1"
        return httpx.Response(
            200,
            json={
                "response": {
                    "data": [
                        {
                            "period": "2026-04-24",
                            "series": "WGTSTUS1",
                            "value": "225500",
                            "units": "MBBL",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await collect_eia_indicators(
            api_key="eia-test",
            base_url="https://api.eia.test",
            series=(
                EiaSeries(
                    "petroleum/stoc/wstk",
                    "WGTSTUS1",
                    "SC",
                    "eia_gasoline_stocks",
                    "MBBL",
                ),
            ),
            client=client,
        )

    assert len(rows) == 1
    assert rows[0].data_type == "eia_gasoline_stocks"


def test_tushare_payload_selects_whitelisted_futures_rows() -> None:
    rows = rows_from_tushare_payload(
        {
            "code": 0,
            "data": {
                "fields": [
                    "ts_code",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "settle",
                    "vol",
                    "oi",
                ],
                "items": [
                    ["RB2510.SHF", "20260430", 3200, 3300, 3180, 3250, 3240, 1000, 3000],
                    ["RB2601.SHF", "20260430", 3210, 3310, 3190, 3260, 3250, 2000, 6000],
                    ["SCTAS2608.INE", "20260430", 1, 1, 1, 1, 1, 1, 1],
                ],
            },
        },
        exchange="SHFE",
        symbols=("RB", "SC"),
    )

    active = dedupe_active_contracts(rows)

    assert len(rows) == 2
    assert len(active) == 1
    assert active[0].symbol == "RB"
    assert active[0].contract_month == "2601"
    assert active[0].exchange == "SHFE"


def test_tushare_payload_rejects_missing_shape() -> None:
    with pytest.raises(RuntimeError, match="data\\.fields/items"):
        rows_from_tushare_payload(
            {"code": 0, "data": {"fields": ["ts_code"], "rows": []}},
            exchange="SHFE",
        )


def test_tushare_payload_rejects_required_field_drift() -> None:
    with pytest.raises(RuntimeError, match="trade_date"):
        rows_from_tushare_payload(
            {
                "code": 0,
                "data": {
                    "fields": ["ts_code", "close"],
                    "items": [["RB2510.SHF", 3250]],
                },
            },
            exchange="SHFE",
        )


async def test_tushare_collector_posts_fut_daily_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_from_request(request)
        assert request.url.path == "/"
        assert payload["api_name"] == "fut_daily"
        assert payload["token"] == "tushare-test"
        assert payload["params"] == {"exchange": "INE"}
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": [
                        "ts_code",
                        "trade_date",
                        "open",
                        "high",
                        "low",
                        "close",
                        "settle",
                        "vol",
                        "oi",
                    ],
                    "items": [["SC2606.INE", "20260430", 590, 600, 580, 595, 594, 100, 500]],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await collect_tushare_market_data(
            token="tushare-test",
            base_url="https://tushare.test",
            exchanges=("INE",),
            symbols=("SC",),
            client=client,
        )

    assert result.errors == []
    assert len(result.rows) == 1
    assert result.rows[0].source_key == "tushare:fut_daily:SC2606.INE:2026-04-30"


def test_parse_csv_tuple_falls_back_to_defaults() -> None:
    assert parse_csv_tuple(" shfe, dce ,,", ("INE",)) == ("SHFE", "DCE")
    assert parse_csv_tuple("", ("INE",)) == ("INE",)


def test_safe_error_message_redacts_query_keys_and_known_secrets() -> None:
    message = safe_error_message(
        "https://example.test/data?api_key=abc123&series_id=X token=secret-token",
        "secret-token",
    )

    assert "abc123" not in message
    assert "secret-token" not in message
    assert "api_key=[redacted]" in message


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


async def test_free_data_ingest_reports_enabled_keyed_sources_without_keys() -> None:
    settings = Settings(
        data_source_fred_enabled=True,
        fred_api_key="",
        data_source_eia_enabled=True,
        eia_api_key="",
        data_source_tushare_enabled=True,
        tushare_token="",
        _env_file=None,
    )

    result = await run_free_data_ingest(object(), settings=settings)  # type: ignore[arg-type]

    assert result.status == "degraded"
    assert result.to_dict()["degraded"] is True
    assert result.source_counts == {"fred": 0, "eia": 0, "tushare": 0}
    assert [error["source"] for error in result.errors] == ["fred", "eia", "tushare"]
    assert all("missing" in error["error"] for error in result.errors)


def test_data_source_registry_marks_keyed_sources() -> None:
    settings = Settings(
        data_source_fred_enabled=True,
        fred_api_key="fred-test",
        data_source_eia_enabled=True,
        eia_api_key="",
        data_source_tushare_enabled=True,
        tushare_token="tushare-test",
        _env_file=None,
    )

    statuses = {status.id: status for status in data_source_statuses(settings)}

    assert statuses["fred"].status == "ready"
    assert statuses["eia"].status == "missing_key"
    assert statuses["tushare"].status == "ready"
    assert statuses["open_meteo"].free_tier == "free_no_key"
    assert statuses["nasa_power"].free_tier == "free_no_key"
    assert statuses["nasa_power_baseline"].free_tier == "free_no_key"
    assert statuses["noaa_cdo"].status == "disabled"
    assert statuses["accuweather"].status == "disabled"


def test_data_source_registry_marks_weather_keyed_sources() -> None:
    settings = Settings(
        data_source_noaa_cdo_enabled=True,
        noaa_cdo_api_key="noaa-test",
        data_source_accuweather_enabled=True,
        accuweather_api_key="",
        _env_file=None,
    )

    statuses = {status.id: status for status in data_source_statuses(settings)}

    assert statuses["noaa_cdo"].status == "ready"
    assert statuses["accuweather"].status == "missing_key"


def test_tushare_csv_tuple_rejects_unbounded_settings() -> None:
    assert parse_csv_tuple("rb, rb, sc", ("RB",)) == ("RB", "SC")

    with pytest.raises(ValueError, match="at most 50"):
        parse_csv_tuple(",".join(f"S{i}" for i in range(51)), ("RB",))

    with pytest.raises(ValueError, match="at most 32"):
        parse_csv_tuple("S" * 33, ("RB",))


def test_data_sources_api_returns_registry_statuses(monkeypatch) -> None:
    def fake_statuses() -> list[DataSourceStatus]:
        return [
            DataSourceStatus(
                id="fred",
                name="FRED",
                category="macro_data",
                enabled=True,
                configured=True,
                requires_key=True,
                free_tier="free_registration",
                status="ready",
                note="ok",
            ),
            DataSourceStatus(
                id="eia",
                name="EIA Open Data",
                category="energy_fundamentals",
                enabled=True,
                configured=False,
                requires_key=True,
                free_tier="free_registration",
                status="missing_key",
                note="key required",
            ),
        ]

    monkeypatch.setattr("app.api.data_sources.data_source_statuses", fake_statuses)

    client = TestClient(create_app())
    response = client.get("/api/data-sources")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "fred",
            "name": "FRED",
            "category": "macro_data",
            "enabled": True,
            "configured": True,
            "requires_key": True,
            "free_tier": "free_registration",
            "status": "ready",
            "note": "ok",
        },
        {
            "id": "eia",
            "name": "EIA Open Data",
            "category": "energy_fundamentals",
            "enabled": True,
            "configured": False,
            "requires_key": True,
            "free_tier": "free_registration",
            "status": "missing_key",
            "note": "key required",
        },
    ]


def test_industry_data_api_rejects_unbounded_query_filters() -> None:
    client = TestClient(create_app())

    oversized_symbol = "S" * 33
    response = client.get(f"/api/industry-data?symbol={oversized_symbol}")
    assert response.status_code == 422

    oversized_type = "x" * 31
    response = client.get(f"/api/industry-data?symbol=SC&data_type={oversized_type}")
    assert response.status_code == 422


def json_from_request(request: httpx.Request) -> dict[str, object]:
    return json.loads(request.content.decode("utf-8"))
