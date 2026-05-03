from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import create_app
from app.models.cost_snapshot import CostSnapshot
from app.services.cost_models.cost_chain import calculate_cost_chain, calculate_symbol_cost
from app.services.cost_models.framework import cost_curve_percentiles
from app.services.cost_models.news_extractor import extract_cost_data_points
from app.services.cost_models.quality import (
    build_quality_report,
    compare_public_benchmarks,
    evaluate_historical_signal_cases,
)
from app.services.cost_models.rubber_sources import (
    public_rubber_inputs,
    public_rubber_source_points,
    rubber_seasonal_factor,
)
from app.services.cost_models.snapshots import build_cost_signal_context, write_cost_snapshot
from app.services.sectors.ferrous import calculate_blast_furnace_margin


class FakeScalars:
    def __init__(self, row=None) -> None:
        self._row = row

    def first(self):
        return self._row


class FakeSession:
    def __init__(self, row=None) -> None:
        self.row = row
        self.rows: list[object] = []
        self.flush_count = 0

    async def scalars(self, _):
        return FakeScalars(self.row)

    def add(self, row: object) -> None:
        self.rows.append(row)
        self.row = row

    async def flush(self) -> None:
        self.flush_count += 1


def test_cost_curve_percentiles_are_monotonic() -> None:
    curve = cost_curve_percentiles(
        100,
        ((-0.1, 0.25), (-0.02, 0.25), (0.05, 0.25), (0.15, 0.25)),
    )

    assert curve["p25"] <= curve["p50"] <= curve["p75"] <= curve["p90"]
    assert curve["p90"] == 115


def test_ferrous_chain_calculates_rebar_from_upstream_costs() -> None:
    chain = calculate_cost_chain(current_prices={"RB": 3200})

    assert chain.symbols == ["JM", "J", "I", "RB", "HC"]
    assert chain.results["J"].unit_cost == 1917.8
    assert chain.results["I"].unit_cost == 880
    assert chain.results["RB"].unit_cost == 3196.9
    assert chain.results["RB"].profit_margin == 0.000969


def test_simulation_overrides_flow_through_downstream_formula() -> None:
    result = calculate_symbol_cost(
        "RB",
        inputs_by_symbol={
            "I": {"iron_ore_index_cny": 700},
            "J": {"coking_processing_fee": 220},
            "RB": {"blast_furnace_conversion_fee": 720},
        },
    )

    assert result.unit_cost < 3196.9
    assert result.breakevens["p75"] > result.breakevens["p50"]


def test_rubber_chain_calculates_ru_from_natural_rubber() -> None:
    chain = calculate_cost_chain(
        symbols=("NR", "RU"),
        inputs_by_symbol={"NR": {"seasonal_factor_pct": 0.02}},
        current_prices={"RU": 15500},
    )

    assert chain.sector == "rubber"
    assert chain.symbols == ["NR", "RU"]
    assert chain.results["NR"].unit_cost == 13260
    assert chain.results["RU"].unit_cost == 15327.8
    assert chain.results["RU"].profit_margin == 0.01111


def test_rubber_public_sources_cover_phase7b_inputs() -> None:
    inputs = public_rubber_inputs()
    source_keys = {point.key for point in public_rubber_source_points()}

    assert {"thai_field_latex_cny", "qingdao_bonded_spot_premium", "ocean_freight"} <= source_keys
    assert inputs["hainan_yunnan_collection_cost"] == 420
    assert rubber_seasonal_factor(1) > rubber_seasonal_factor(8)


def test_blast_furnace_margin_uses_phase7a_formula() -> None:
    margin = calculate_blast_furnace_margin(
        rebar_price=3600,
        iron_ore_price=850,
        coke_price=1900,
        conversion_fee=760,
    )

    assert margin.margin == 530
    assert margin.margin_pct == 530 / 3600


async def test_write_cost_snapshot_creates_row_from_result() -> None:
    session = FakeSession()
    result = calculate_symbol_cost("RB", current_prices={"RB": 3200})

    row = await write_cost_snapshot(
        session,  # type: ignore[arg-type]
        result,
        snapshot_date=date(2026, 5, 3),
    )

    assert isinstance(row, CostSnapshot)
    assert row.symbol == "RB"
    assert row.snapshot_date == date(2026, 5, 3)
    assert row.breakeven_p90 > row.breakeven_p50
    assert session.flush_count == 1


def test_build_cost_signal_context_serializes_snapshot_history() -> None:
    rows = [
        CostSnapshot(
            symbol="RB",
            name="Rebar",
            sector="ferrous",
            snapshot_date=date(2026, 5, 2 + idx),
            current_price=95 + idx,
            total_unit_cost=100,
            breakeven_p25=90,
            breakeven_p50=100,
            breakeven_p75=110,
            breakeven_p90=120,
            profit_margin=-0.04 + idx * 0.01,
            cost_breakdown=[],
            inputs={},
            data_sources=[],
            uncertainty_pct=0.05,
            formula_version="phase7a.v1",
        )
        for idx in range(2)
    ]

    context = build_cost_signal_context("RB", rows)

    assert context is not None
    assert context["symbol1"] == "RB"
    assert context["regime"] == "cost_model"
    assert len(context["cost_snapshots"]) == 2


def test_public_benchmark_comparisons_pass_phase7a_tolerance() -> None:
    chain = calculate_cost_chain()
    snapshots = {
        symbol: CostSnapshot(
            snapshot_date=date(2026, 5, 3),
            **result.to_snapshot_payload(),
        )
        for symbol, result in chain.results.items()
    }

    comparisons = compare_public_benchmarks(snapshots)

    assert len(comparisons) >= 5
    assert max(item.error_pct for item in comparisons) < 5
    assert all(item.within_tolerance for item in comparisons)


async def test_quality_report_recommends_deferring_paid_feed_when_checks_pass() -> None:
    chain = calculate_cost_chain()
    snapshots = {
        symbol: CostSnapshot(
            snapshot_date=date(2026, 5, 3),
            **result.to_snapshot_payload(),
        )
        for symbol, result in chain.results.items()
    }
    comparisons = compare_public_benchmarks(snapshots)
    signal_cases = await evaluate_historical_signal_cases()

    report = build_quality_report(comparisons=comparisons, signal_cases=signal_cases)

    assert report.benchmark_error_avg_pct < 5
    assert report.signal_case_hit_rate == 1.0
    assert report.paid_data_recommendation == "defer_paid_purchase_monitor_weekly"
    assert report.preferred_vendor is None


def test_news_extractor_finds_cost_data_points() -> None:
    points = extract_cost_data_points(
        title="Iron ore freight rises",
        content="Iron ore spot freight reached 62 yuan per tonne.",
        source="public-news",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )

    assert points[0].symbol == "I"
    assert points[0].component == "freight"
    assert points[0].value == 62


def test_simulation_api_returns_cost_breakdown() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/cost-models/RB/simulate",
        json={
            "inputs_by_symbol": {
                "I": {"iron_ore_index_cny": 700},
                "RB": {"blast_furnace_conversion_fee": 720},
            },
            "current_prices": {"RB": 3300},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "RB"
    assert payload["total_unit_cost"] < 3196.9
    assert payload["breakevens"]["p90"] > payload["breakevens"]["p50"]
    assert payload["profit_margin"] > 0


def test_rubber_simulation_api_returns_cost_breakdown() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/cost-models/RU/simulate",
        json={
            "inputs_by_symbol": {
                "NR": {"seasonal_factor_pct": 0.02, "thai_field_latex_cny": 11000},
                "RU": {"ru_processing_fee": 900},
            },
            "current_prices": {"RU": 15400},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "RU"
    assert payload["sector"] == "rubber"
    assert payload["total_unit_cost"] < 15327.8
    assert payload["breakevens"]["p90"] > payload["breakevens"]["p50"]


def test_quality_api_returns_report(monkeypatch) -> None:
    chain = calculate_cost_chain()
    snapshots = {
        symbol: CostSnapshot(
            snapshot_date=date(2026, 5, 3),
            **result.to_snapshot_payload(),
        )
        for symbol, result in chain.results.items()
    }

    async def fake_report(_session):
        return build_quality_report(
            comparisons=compare_public_benchmarks(snapshots),
            signal_cases=await evaluate_historical_signal_cases(),
        )

    async def fake_db():
        yield object()

    monkeypatch.setattr("app.api.cost_models.run_ferrous_quality_report", fake_report)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/cost-models/quality/ferrous")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sector"] == "ferrous"
    assert payload["benchmark_pass_rate"] >= 0.8
    assert payload["signal_case_hit_rate"] == 1.0
