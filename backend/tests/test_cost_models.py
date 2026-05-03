from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.cost_snapshot import CostSnapshot
from app.services.cost_models.cost_chain import calculate_cost_chain, calculate_symbol_cost
from app.services.cost_models.framework import cost_curve_percentiles
from app.services.cost_models.news_extractor import extract_cost_data_points
from app.services.cost_models.snapshots import write_cost_snapshot
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
