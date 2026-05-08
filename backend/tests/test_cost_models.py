import asyncio
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import create_app
from app.models.cost_snapshot import CostSnapshot
from app.services.cost_models.cost_chain import calculate_cost_chain, calculate_symbol_cost
from app.services.cost_models.framework import cost_curve_percentiles
from app.services.cost_models.news_extractor import extract_cost_data_points
from app.services.cost_models.quality import (
    PUBLIC_RUBBER_BENCHMARKS,
    SignalCaseResult,
    _evaluate_signal_cases,
    _evaluate_trigger_results,
    build_quality_report,
    compare_public_benchmarks,
    evaluate_historical_signal_cases,
    evaluate_historical_rubber_signal_cases,
    latest_or_calculated_snapshots,
)
from app.services.cost_models.rubber_sources import (
    production_rubber_fallback_inputs,
    production_rubber_source_specs,
    public_rubber_inputs,
    public_rubber_source_points,
    rubber_seasonal_factor,
)
from app.services.cost_models.snapshots import (
    build_cost_signal_context,
    cost_histories_for_symbols,
    cost_signal_contexts,
    current_prices_for_symbols,
    latest_cost_snapshots,
    write_cost_snapshot,
    write_cost_snapshots,
)
from app.services.pipeline.handlers import trigger_context_from_payload
from app.services.sectors.ferrous import calculate_blast_furnace_margin
from app.services.signals.detector import SignalDetector
from app.services.signals.types import TriggerContext, TriggerResult


class FakeScalars:
    def __init__(self, row=None, rows=None) -> None:
        self._rows = rows if rows is not None else ([row] if row is not None else [])

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class FakeResult:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, row=None, result_rows=None, scalar_rows=None) -> None:
        self.row = row
        self.result_rows = result_rows or []
        self.execute_count = 0
        self.scalar_rows = scalar_rows
        self.scalars_count = 0
        self.rows: list[object] = []
        self.flush_count = 0

    async def scalars(self, _):
        self.scalars_count += 1
        if self.scalar_rows is not None:
            return FakeScalars(rows=self.scalar_rows)
        return FakeScalars(self.row)

    async def execute(self, _):
        self.execute_count += 1
        return FakeResult(self.result_rows)

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


def test_rubber_production_source_specs_cover_phase7b_targets() -> None:
    specs = production_rubber_source_specs()
    components = {spec.component for spec in specs}
    fallback_inputs = production_rubber_fallback_inputs()

    assert {
        "qingdao_bonded_spot_premium",
        "hainan_yunnan_collection_cost",
        "thai_field_latex_cny",
        "ocean_freight",
    } <= components
    assert all(spec.quality == "production_candidate" for spec in specs)
    assert fallback_inputs["thai_field_latex_cny"] == 11200


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


async def test_current_prices_for_symbols_uses_single_batch_query() -> None:
    session = FakeSession(result_rows=[("RB", 3200), ("I", 850)])

    prices = await current_prices_for_symbols(
        session,  # type: ignore[arg-type]
        ("RB", "I", "NR"),
    )

    assert prices == {"RB": 3200.0, "I": 850.0, "NR": None}
    assert session.execute_count == 1


async def test_write_cost_snapshots_prefetches_existing_rows_once() -> None:
    existing = cost_snapshot_row("RB", date(2026, 5, 3))
    session = FakeSession(scalar_rows=[existing])
    results = [
        calculate_symbol_cost("RB", current_prices={"RB": 3200}),
        calculate_symbol_cost("HC", current_prices={"HC": 3300}),
    ]

    rows = await write_cost_snapshots(
        session,  # type: ignore[arg-type]
        results,
        snapshot_date=date(2026, 5, 3),
    )

    assert [row.symbol for row in rows] == ["RB", "HC"]
    assert rows[0] is existing
    assert rows[0].current_price == 3200
    assert rows[1] in session.rows
    assert session.scalars_count == 1
    assert session.flush_count == 1


async def test_latest_cost_snapshots_uses_single_batch_query() -> None:
    rows = [
        cost_snapshot_row("RB", date(2026, 5, 3)),
        cost_snapshot_row("I", date(2026, 5, 3)),
    ]
    session = FakeSession(scalar_rows=rows)

    snapshots = await latest_cost_snapshots(
        session,  # type: ignore[arg-type]
        ("RB", "I", "HC"),
    )

    assert set(snapshots) == {"RB", "I"}
    assert snapshots["RB"].symbol == "RB"
    assert session.scalars_count == 1


async def test_cost_histories_for_symbols_uses_single_batch_query() -> None:
    rows = [
        cost_snapshot_row("RB", date(2026, 5, 4)),
        cost_snapshot_row("RB", date(2026, 5, 3)),
        cost_snapshot_row("I", date(2026, 5, 4)),
    ]
    session = FakeSession(scalar_rows=rows)

    histories = await cost_histories_for_symbols(
        session,  # type: ignore[arg-type]
        symbols=("RB", "I", "HC"),
        limit_per_symbol=2,
    )

    assert list(histories) == ["RB", "I", "HC"]
    assert [row.symbol for row in histories["RB"]] == ["RB", "RB"]
    assert [row.symbol for row in histories["I"]] == ["I"]
    assert histories["HC"] == []
    assert session.scalars_count == 1


async def test_cost_signal_contexts_uses_single_batch_query() -> None:
    rows = [
        cost_snapshot_row("RB", date(2026, 5, 4)),
        cost_snapshot_row("RB", date(2026, 5, 3)),
        cost_snapshot_row("I", date(2026, 5, 4)),
    ]
    session = FakeSession(scalar_rows=rows)

    contexts = await cost_signal_contexts(
        session,  # type: ignore[arg-type]
        symbols=("RB", "I", "HC"),
        limit_per_symbol=2,
    )

    assert [context["symbol1"] for context in contexts] == ["RB", "I"]
    assert len(contexts[0]["cost_snapshots"]) == 2
    assert session.scalars_count == 1


async def test_latest_or_calculated_snapshots_calculates_known_chain_with_single_price_query() -> None:
    session = FakeSession(
        scalar_rows=[],
        result_rows=[
            ("JM", 1100),
            ("J", 1900),
            ("I", 820),
            ("RB", 3300),
            ("HC", 3400),
        ],
    )

    snapshots = await latest_or_calculated_snapshots(
        session,  # type: ignore[arg-type]
        ("JM", "J", "I", "RB", "HC"),
    )

    assert set(snapshots) == {"JM", "J", "I", "RB", "HC"}
    assert snapshots["RB"].current_price == 3300
    assert snapshots["RB"].breakeven_p90 > snapshots["RB"].breakeven_p50
    assert session.scalars_count == 1
    assert session.execute_count == 1


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


def test_cost_histories_api_batches_requested_symbols(monkeypatch) -> None:
    captured: dict[str, object] = {}
    session = object()

    async def fake_db():
        yield session

    async def fake_cost_histories_for_symbols(db_session, *, symbols, limit_per_symbol):
        captured["session"] = db_session
        captured["symbols"] = symbols
        captured["limit"] = limit_per_symbol
        return {
            "RB": [cost_snapshot_row("RB", date(2026, 5, 4))],
            "HC": [cost_snapshot_row("HC", date(2026, 5, 4))],
        }

    monkeypatch.setattr(
        "app.api.cost_models.cost_histories_for_symbols",
        fake_cost_histories_for_symbols,
    )
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/cost-models/histories?symbols=rb,hc,rb&limit=3")

    assert response.status_code == 200
    assert captured == {"session": session, "symbols": ("RB", "HC"), "limit": 3}
    assert set(response.json()) == {"RB", "HC"}


def test_parse_cost_symbols_rejects_empty_after_normalization() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/cost-models/histories?symbols=,,,")

    assert response.status_code == 400
    assert response.json()["detail"] == "symbols must include at least one value"


def test_parse_cost_symbols_rejects_too_many_unique_values() -> None:
    app = create_app()
    client = TestClient(app)
    symbols = ",".join(f"S{i}" for i in range(41))

    response = client.get(f"/api/cost-models/histories?symbols={symbols}")

    assert response.status_code == 400
    assert "at most 40" in response.json()["detail"]


def test_parse_cost_symbols_rejects_oversized_symbol() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get(f"/api/cost-models/histories?symbols={'X' * 21}")

    assert response.status_code == 400
    assert "at most 20" in response.json()["detail"]


def test_parse_cost_symbols_rejects_oversized_query() -> None:
    app = create_app()
    client = TestClient(app)
    symbols = ",".join("RB" for _ in range(600))

    response = client.get(f"/api/cost-models/histories?symbols={symbols}")

    assert response.status_code == 422


def test_cost_model_path_symbols_are_bounded() -> None:
    app = create_app()
    client = TestClient(app)
    oversized = "X" * 21

    responses = [
        client.get(f"/api/cost-models/{oversized}"),
        client.get(f"/api/cost-models/{oversized}/history"),
        client.get(f"/api/cost-models/{oversized}/chain"),
        client.post(
            f"/api/cost-models/{oversized}/simulate",
            json={"inputs_by_symbol": {}, "current_prices": {}},
        ),
    ]

    assert {response.status_code for response in responses} == {422}


def cost_snapshot_row(symbol: str, snapshot_date: date) -> CostSnapshot:
    return CostSnapshot(
        id=uuid4(),
        symbol=symbol,
        name=symbol,
        sector="ferrous",
        snapshot_date=snapshot_date,
        current_price=100,
        total_unit_cost=95,
        breakeven_p25=90,
        breakeven_p50=95,
        breakeven_p75=100,
        breakeven_p90=105,
        profit_margin=0.05,
        cost_breakdown=[],
        inputs={},
        data_sources=[],
        uncertainty_pct=0.05,
        formula_version="test.v1",
        created_at=datetime.combine(snapshot_date, datetime.min.time(), timezone.utc),
    )


def trigger_result(signal_type: str) -> TriggerResult:
    return TriggerResult(
        signal_type=signal_type,
        triggered=True,
        severity="medium",
        confidence=0.7,
        trigger_chain=[],
        related_assets=["RB"],
        risk_items=[],
        manual_check_items=[],
        title=signal_type,
        summary=signal_type,
    )


async def test_rubber_cost_context_triggers_profit_margin_signals() -> None:
    rows = [
        CostSnapshot(
            symbol="RU",
            name="SHFE Rubber",
            sector="rubber",
            snapshot_date=date(2026, 5, 3),
            current_price=14000,
            total_unit_cost=15327.8,
            breakeven_p25=14867.966,
            breakeven_p50=14867.966,
            breakeven_p75=16094.19,
            breakeven_p90=17473.692,
            profit_margin=-0.094843,
            cost_breakdown=[],
            inputs={},
            data_sources=[],
            uncertainty_pct=0.07,
            formula_version="phase7b.v1",
        )
    ]
    payload = build_cost_signal_context("RU", rows)

    assert payload is not None
    context = trigger_context_from_payload(payload)
    results = await SignalDetector().detect(
        context,
        signal_types={"median_pressure", "marginal_capacity_squeeze"},
    )

    assert {result.signal_type for result in results} == {
        "median_pressure",
        "marginal_capacity_squeeze",
    }
    assert all("RU" in result.related_assets for result in results)


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


async def test_quality_evaluator_helper_runs_independent_evaluators_concurrently() -> None:
    gate = asyncio.Event()
    context = TriggerContext(
        symbol1="RB",
        category="ferrous",
        timestamp=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )

    class WaitingEvaluator:
        signal_type = "waiting"

        async def evaluate(self, _context):
            await gate.wait()
            return trigger_result(self.signal_type)

    class ReleasingEvaluator:
        signal_type = "releasing"

        async def evaluate(self, _context):
            gate.set()
            return trigger_result(self.signal_type)

    results = await asyncio.wait_for(
        _evaluate_trigger_results(
            context,
            (WaitingEvaluator(), ReleasingEvaluator()),  # type: ignore[arg-type]
        ),
        timeout=0.2,
    )

    assert [result.signal_type for result in results] == ["waiting", "releasing"]


async def test_quality_evaluator_helper_keeps_successful_results_when_peer_fails() -> None:
    context = TriggerContext(
        symbol1="RB",
        category="ferrous",
        timestamp=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )

    class FailingEvaluator:
        signal_type = "failing"

        async def evaluate(self, _context):
            raise RuntimeError("quality evaluator failed")

    class PassingEvaluator:
        signal_type = "passing"

        async def evaluate(self, _context):
            return trigger_result(self.signal_type)

    results = await _evaluate_trigger_results(
        context,
        (FailingEvaluator(), PassingEvaluator()),  # type: ignore[arg-type]
    )

    assert [result.signal_type for result in results] == ["passing"]


async def test_quality_signal_case_helper_converts_case_errors_to_failed_results() -> None:
    async def passing_case():
        return SignalCaseResult(
            case_id="passing-case",
            title="Passing case",
            expected_signals=["passing"],
            triggered_signals=["passing"],
            passed=True,
            note="ok",
        )

    async def failing_case():
        raise RuntimeError("case failed")

    results = await _evaluate_signal_cases(
        (
            ("passing-case", "Passing case", passing_case()),
            ("failing-case", "Failing case", failing_case()),
        )
    )

    assert [result.case_id for result in results] == ["passing-case", "failing-case"]
    assert results[0].passed is True
    assert results[1].passed is False
    assert results[1].expected_signals == ["case_evaluation"]
    assert results[1].triggered_signals == []
    assert results[1].note == "Case evaluation failed: case failed"


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


async def test_rubber_quality_report_validates_public_breakevens() -> None:
    chain = calculate_cost_chain(symbols=("NR", "RU"))
    snapshots = {
        symbol: CostSnapshot(
            snapshot_date=date(2026, 5, 3),
            **result.to_snapshot_payload(),
        )
        for symbol, result in chain.results.items()
    }
    comparisons = compare_public_benchmarks(snapshots, PUBLIC_RUBBER_BENCHMARKS)
    signal_cases = await evaluate_historical_rubber_signal_cases()

    report = build_quality_report(
        sector="rubber",
        comparisons=comparisons,
        signal_cases=signal_cases,
    )

    assert report.sector == "rubber"
    assert report.benchmark_error_avg_pct < 2
    assert report.signal_case_hit_rate == 1.0
    assert report.paid_data_recommendation == "defer_paid_purchase_monitor_weekly"


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


def test_news_extractor_finds_rubber_cost_data_points() -> None:
    points = extract_cost_data_points(
        title="Qingdao bonded natural rubber spot premium rises",
        content=(
            "Qingdao bonded rubber spot premium reached 320 yuan per tonne; "
            "Thailand latex quote 11200 yuan."
        ),
        source="public-rubber-feed",
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
    )

    components = {point.component for point in points}
    symbols = {point.symbol for point in points}

    assert {"RU", "NR"} <= symbols
    assert "qingdao_bonded_spot_premium" in components
    assert "thai_field_latex_cny" in components


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


def test_simulation_api_normalizes_contract_symbol_payloads() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/cost-models/rb2506/simulate",
        json={
            "inputs_by_symbol": {
                "i2509": {"iron_ore_index_cny": 700},
                "rb2506": {"blast_furnace_conversion_fee": 720},
            },
            "current_prices": {"rb2506": 3300},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "RB"
    assert payload["current_price"] == 3300
    assert payload["inputs"]["blast_furnace_conversion_fee"]["value"] == 720
    assert payload["inputs"]["upstream_i_unit_cost"]["value"] == 820
    assert payload["total_unit_cost"] == 3060.9


def test_simulation_api_rejects_oversized_input_symbol_set() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/cost-models/RB/simulate",
        json={
            "inputs_by_symbol": {f"S{index}": {"value": 1} for index in range(21)},
            "current_prices": {"RB": 3300},
        },
    )

    assert response.status_code == 422


def test_simulation_api_rejects_invalid_numeric_inputs() -> None:
    client = TestClient(create_app())

    negative_price = client.post(
        "/api/cost-models/RB/simulate",
        json={
            "inputs_by_symbol": {"RB": {"blast_furnace_conversion_fee": 720}},
            "current_prices": {"RB": -1},
        },
    )
    oversized_input = client.post(
        "/api/cost-models/RB/simulate",
        json={
            "inputs_by_symbol": {"RB": {"blast_furnace_conversion_fee": 1_000_001}},
            "current_prices": {"RB": 3300},
        },
    )

    assert negative_price.status_code == 422
    assert oversized_input.status_code == 422


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


def test_rubber_quality_api_returns_report(monkeypatch) -> None:
    chain = calculate_cost_chain(symbols=("NR", "RU"))
    snapshots = {
        symbol: CostSnapshot(
            snapshot_date=date(2026, 5, 3),
            **result.to_snapshot_payload(),
        )
        for symbol, result in chain.results.items()
    }

    async def fake_report(_session):
        return build_quality_report(
            sector="rubber",
            comparisons=compare_public_benchmarks(snapshots, PUBLIC_RUBBER_BENCHMARKS),
            signal_cases=await evaluate_historical_rubber_signal_cases(),
        )

    async def fake_db():
        yield object()

    monkeypatch.setattr("app.api.cost_models.run_rubber_quality_report", fake_report)
    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)

    response = client.get("/api/cost-models/quality/rubber")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sector"] == "rubber"
    assert payload["benchmark_pass_rate"] == 1.0
    assert payload["signal_case_hit_rate"] == 1.0
