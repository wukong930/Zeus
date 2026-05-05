import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_snapshot import CostSnapshot
from app.services.cost_models.cost_chain import (
    FERROUS_CHAIN_ORDER,
    RUBBER_CHAIN_ORDER,
    calculate_cost_chain,
)
from app.services.cost_models.snapshots import (
    calculate_cost_snapshot,
    current_prices_for_symbols,
    latest_cost_snapshots,
)
from app.services.signals.evaluators.cost_model import (
    CapacityContractionEvaluator,
    MarginalCapacitySqueezeEvaluator,
    MedianPressureEvaluator,
    RestartExpectationEvaluator,
)
from app.services.signals.evaluators.rubber_supply import RubberSupplyShockEvaluator
from app.services.signals.types import (
    CostSnapshotPoint,
    NewsEventPoint,
    TriggerContext,
    TriggerEvaluator,
    TriggerResult,
)

ACCEPTABLE_BENCHMARK_ERROR_PCT = 5.0
MIN_SIGNAL_CASE_HIT_RATE = 0.75

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublicBenchmark:
    symbol: str
    metric: str
    public_value: float
    source: str
    observed_at: datetime
    note: str


@dataclass(frozen=True)
class BenchmarkComparison:
    symbol: str
    metric: str
    model_value: float
    public_value: float
    error_pct: float
    within_tolerance: bool
    source: str
    observed_at: datetime
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "metric": self.metric,
            "model_value": round(self.model_value, 4),
            "public_value": round(self.public_value, 4),
            "error_pct": round(self.error_pct, 4),
            "within_tolerance": self.within_tolerance,
            "source": self.source,
            "observed_at": self.observed_at.isoformat(),
            "note": self.note,
        }


@dataclass(frozen=True)
class SignalCaseResult:
    case_id: str
    title: str
    expected_signals: list[str]
    triggered_signals: list[str]
    passed: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "title": self.title,
            "expected_signals": self.expected_signals,
            "triggered_signals": self.triggered_signals,
            "passed": self.passed,
            "note": self.note,
        }


@dataclass(frozen=True)
class CostQualityReport:
    sector: str
    generated_at: datetime
    benchmark_error_avg_pct: float
    benchmark_error_max_pct: float
    benchmark_pass_rate: float
    signal_case_hit_rate: float
    data_quality_score: int
    paid_data_recommendation: str
    preferred_vendor: str | None
    benchmark_comparisons: list[BenchmarkComparison]
    signal_cases: list[SignalCaseResult]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sector": self.sector,
            "generated_at": self.generated_at.isoformat(),
            "benchmark_error_avg_pct": round(self.benchmark_error_avg_pct, 4),
            "benchmark_error_max_pct": round(self.benchmark_error_max_pct, 4),
            "benchmark_pass_rate": round(self.benchmark_pass_rate, 4),
            "signal_case_hit_rate": round(self.signal_case_hit_rate, 4),
            "data_quality_score": self.data_quality_score,
            "paid_data_recommendation": self.paid_data_recommendation,
            "preferred_vendor": self.preferred_vendor,
            "benchmark_comparisons": [item.to_dict() for item in self.benchmark_comparisons],
            "signal_cases": [item.to_dict() for item in self.signal_cases],
            "limitations": self.limitations,
        }


PUBLIC_FERROUS_BENCHMARKS: tuple[PublicBenchmark, ...] = (
    PublicBenchmark(
        symbol="RB",
        metric="breakeven_p75",
        public_value=3400.0,
        source="phase7a_public_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Composite public steel-margin commentary reference for rebar high-cost mills.",
    ),
    PublicBenchmark(
        symbol="RB",
        metric="breakeven_p90",
        public_value=3600.0,
        source="phase7a_public_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Composite public steel-margin commentary reference for marginal rebar capacity.",
    ),
    PublicBenchmark(
        symbol="HC",
        metric="breakeven_p75",
        public_value=3700.0,
        source="phase7a_public_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Hot-coil public breakeven estimate adjusted by hot-rolling spread.",
    ),
    PublicBenchmark(
        symbol="J",
        metric="breakeven_p75",
        public_value=2050.0,
        source="phase7a_public_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Coke public full-cost estimate from raw coal ratio and processing fee commentary.",
    ),
    PublicBenchmark(
        symbol="I",
        metric="breakeven_p50",
        public_value=830.0,
        source="phase7a_public_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Iron ore landing-cost public estimate using spot index, freight, and port fees.",
    ),
    PublicBenchmark(
        symbol="JM",
        metric="breakeven_p50",
        public_value=1120.0,
        source="phase7a_public_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Coking-coal public full-cost estimate from mining, washing, rail, and tax components.",
    ),
)

PUBLIC_RUBBER_BENCHMARKS: tuple[PublicBenchmark, ...] = (
    PublicBenchmark(
        symbol="NR",
        metric="breakeven_p50",
        public_value=12800.0,
        source="phase7b_public_rubber_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="Natural-rubber public origin basket estimate from SEA and domestic origin references.",
    ),
    PublicBenchmark(
        symbol="NR",
        metric="breakeven_p90",
        public_value=15650.0,
        source="phase7b_public_rubber_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="High-cost origin estimate including seasonal/tapping stress premium.",
    ),
    PublicBenchmark(
        symbol="RU",
        metric="breakeven_p50",
        public_value=14950.0,
        source="phase7b_public_rubber_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="SHFE RU midpoint breakeven from NR input, processing, grade, warehouse and delivery fees.",
    ),
    PublicBenchmark(
        symbol="RU",
        metric="breakeven_p75",
        public_value=16100.0,
        source="phase7b_public_rubber_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="RU high-cost producer estimate for marginal cost-pressure monitoring.",
    ),
    PublicBenchmark(
        symbol="RU",
        metric="breakeven_p90",
        public_value=17500.0,
        source="phase7b_public_rubber_reference_pack",
        observed_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        note="RU marginal capacity estimate used for supply squeeze validation.",
    ),
)


async def run_ferrous_quality_report(session: AsyncSession) -> CostQualityReport:
    snapshots = await latest_or_calculated_snapshots(session, FERROUS_CHAIN_ORDER)
    comparisons = compare_public_benchmarks(snapshots, PUBLIC_FERROUS_BENCHMARKS)
    signal_cases = await evaluate_historical_signal_cases()
    return build_quality_report(
        sector="ferrous",
        comparisons=comparisons,
        signal_cases=signal_cases,
        limitations=[
            "Reference pack is a public-source bootstrap, not a licensed Mysteel/SMM/Zhuochuang feed.",
            "Low-frequency inputs still use manual/public fallbacks and should be reviewed quarterly.",
            "Historical signal cases validate trigger logic, not full forward PnL without deeper archived data.",
        ],
    )


async def run_rubber_quality_report(session: AsyncSession) -> CostQualityReport:
    snapshots = await latest_or_calculated_snapshots(session, RUBBER_CHAIN_ORDER)
    comparisons = compare_public_benchmarks(snapshots, PUBLIC_RUBBER_BENCHMARKS)
    signal_cases = await evaluate_historical_rubber_signal_cases()
    return build_quality_report(
        sector="rubber",
        comparisons=comparisons,
        signal_cases=signal_cases,
        limitations=[
            "Rubber reference pack validates public breakeven reasonableness, not licensed Zhuochuang/SMM prices.",
            "Production source specs are ready for Qingdao, Hainan/Yunnan, SEA export, and freight feeds.",
            "Origin-weather signal cases validate event recognition; deeper archived PnL is still a Phase 8/learning task.",
        ],
    )


async def latest_or_calculated_snapshots(
    session: AsyncSession,
    symbols: tuple[str, ...] = FERROUS_CHAIN_ORDER,
) -> dict[str, CostSnapshot]:
    snapshots = await latest_cost_snapshots(session, symbols)
    missing_symbols = tuple(symbol.upper() for symbol in symbols if symbol.upper() not in snapshots)
    if not missing_symbols:
        return snapshots

    if symbols in {FERROUS_CHAIN_ORDER, RUBBER_CHAIN_ORDER}:
        current_prices = await current_prices_for_symbols(session, symbols)
        chain = calculate_cost_chain(symbols=symbols, current_prices=current_prices)
        snapshot_date = datetime.now(timezone.utc).date()
        for symbol in missing_symbols:
            snapshots[symbol] = CostSnapshot(
                snapshot_date=snapshot_date,
                **chain.results[symbol].to_snapshot_payload(),
            )
        return snapshots

    for symbol in missing_symbols:
        normalized = symbol.upper()
        result = await calculate_cost_snapshot(session, normalized)
        payload = result.to_snapshot_payload()
        snapshots[normalized] = CostSnapshot(
            snapshot_date=datetime.now(timezone.utc).date(),
            **payload,
        )
    return snapshots


def compare_public_benchmarks(
    snapshots: dict[str, CostSnapshot],
    benchmarks: tuple[PublicBenchmark, ...] = PUBLIC_FERROUS_BENCHMARKS,
) -> list[BenchmarkComparison]:
    comparisons: list[BenchmarkComparison] = []
    for benchmark in benchmarks:
        row = snapshots.get(benchmark.symbol)
        if row is None:
            continue
        model_value = float(getattr(row, benchmark.metric))
        error_pct = (
            abs(model_value - benchmark.public_value) / benchmark.public_value * 100
            if benchmark.public_value
            else 0.0
        )
        comparisons.append(
            BenchmarkComparison(
                symbol=benchmark.symbol,
                metric=benchmark.metric,
                model_value=model_value,
                public_value=benchmark.public_value,
                error_pct=error_pct,
                within_tolerance=error_pct <= ACCEPTABLE_BENCHMARK_ERROR_PCT,
                source=benchmark.source,
                observed_at=benchmark.observed_at,
                note=benchmark.note,
            )
        )
    return comparisons


async def evaluate_historical_signal_cases() -> list[SignalCaseResult]:
    return list(
        await asyncio.gather(
            evaluate_signal_case(
                case_id="ferrous-2021-production-curb",
                title="2021 production curb cost pressure",
                snapshots=[
                    synthetic_cost_snapshot(idx, price=92, unit_cost=100, margin=-0.087)
                    for idx in range(10)
                ],
                expected_signals=[
                    "capacity_contraction",
                    "median_pressure",
                    "marginal_capacity_squeeze",
                ],
                note="Two-week negative margin plus price below P50/P75 should surface capacity pressure.",
            ),
            evaluate_signal_case(
                case_id="ferrous-2024-capacity-adjustment",
                title="2024 capacity adjustment marginal squeeze",
                snapshots=[synthetic_cost_snapshot(0, price=96, unit_cost=100, margin=-0.042)],
                expected_signals=["median_pressure", "marginal_capacity_squeeze"],
                note="Known adjustment windows are represented by price below median and marginal breakevens.",
            ),
            evaluate_signal_case(
                case_id="ferrous-margin-restart",
                title="Margin recovery restart expectation",
                snapshots=[
                    synthetic_cost_snapshot(0, price=96, unit_cost=100, margin=-0.04),
                    synthetic_cost_snapshot(1, price=98, unit_cost=100, margin=-0.02),
                    synthetic_cost_snapshot(2, price=103, unit_cost=100, margin=0.029),
                ],
                expected_signals=["restart_expectation"],
                note="A move from negative to positive margin should trigger restart expectation.",
            ),
        )
    )


async def evaluate_historical_rubber_signal_cases() -> list[SignalCaseResult]:
    return list(
        await asyncio.gather(
            evaluate_signal_case(
                case_id="rubber-ru-marginal-squeeze",
                title="RU price below rubber cost curve",
                snapshots=[
                    synthetic_cost_snapshot(
                        0,
                        symbol="RU",
                        price=14000,
                        unit_cost=15327.8,
                        p25=14867.966,
                        p50=14867.966,
                        p75=16094.19,
                        p90=17473.692,
                        margin=-0.094843,
                    )
                ],
                expected_signals=["median_pressure", "marginal_capacity_squeeze"],
                note="RU below P50/P75 should surface rubber margin pressure.",
                symbol="RU",
                category="rubber",
            ),
            evaluate_news_signal_case(
                case_id="rubber-2019-thai-drought",
                title="2019 Thai drought rubber supply stress",
                event=synthetic_rubber_news_event(
                    "rubber-2019-thai-drought",
                    "Thailand drought cuts natural rubber tapping",
                    "Dry weather in Thai rubber producing regions lowers field latex flow.",
                ),
                expected_signals=["rubber_supply_shock"],
                note="Thai drought maps to NR/RU supply stress through origin tapping disruption.",
            ),
            evaluate_news_signal_case(
                case_id="rubber-2020-covid-tapping",
                title="2020 tapping disruption during Covid restrictions",
                event=synthetic_rubber_news_event(
                    "rubber-2020-covid-tapping",
                    "Malaysia rubber tapping disruption during Covid restrictions",
                    "Movement restrictions disrupt rubber tapping and export logistics.",
                ),
                expected_signals=["rubber_supply_shock"],
                note="Covid-era tapping/logistics restrictions should be visible as rubber supply shock.",
            ),
        )
    )


async def evaluate_signal_case(
    *,
    case_id: str,
    title: str,
    snapshots: list[CostSnapshotPoint],
    expected_signals: list[str],
    note: str,
    symbol: str = "RB",
    category: str = "ferrous",
) -> SignalCaseResult:
    context = TriggerContext(
        symbol1=symbol,
        category=category,
        timestamp=snapshots[-1].timestamp if snapshots else datetime.now(timezone.utc),
        cost_snapshots=snapshots,
    )
    evaluators = (
        CapacityContractionEvaluator(),
        RestartExpectationEvaluator(),
        MedianPressureEvaluator(),
        MarginalCapacitySqueezeEvaluator(),
    )
    triggered = [
        result.signal_type
        for result in await _evaluate_trigger_results(context, evaluators)
    ]
    return SignalCaseResult(
        case_id=case_id,
        title=title,
        expected_signals=expected_signals,
        triggered_signals=triggered,
        passed=set(expected_signals).issubset(triggered),
        note=note,
    )


async def evaluate_news_signal_case(
    *,
    case_id: str,
    title: str,
    event: NewsEventPoint,
    expected_signals: list[str],
    note: str,
) -> SignalCaseResult:
    context = TriggerContext(
        symbol1="RU",
        category="rubber",
        timestamp=event.published_at,
        news_events=[event],
    )
    evaluators = (RubberSupplyShockEvaluator(),)
    triggered = [
        result.signal_type
        for result in await _evaluate_trigger_results(context, evaluators)
    ]
    return SignalCaseResult(
        case_id=case_id,
        title=title,
        expected_signals=expected_signals,
        triggered_signals=triggered,
        passed=set(expected_signals).issubset(triggered),
        note=note,
    )


async def _evaluate_trigger_results(
    context: TriggerContext,
    evaluators: tuple[TriggerEvaluator, ...],
) -> list[TriggerResult]:
    results = await asyncio.gather(
        *(evaluator.evaluate(context) for evaluator in evaluators),
        return_exceptions=True,
    )
    valid_results: list[TriggerResult] = []
    for evaluator, result in zip(evaluators, results, strict=True):
        if isinstance(result, BaseException):
            if not isinstance(result, Exception):
                raise result
            logger.warning(
                "Cost quality evaluator %s failed for %s/%s",
                evaluator.signal_type,
                context.symbol1,
                context.symbol2 or context.category,
                exc_info=(type(result), result, result.__traceback__),
            )
            continue
        if result is not None:
            valid_results.append(result)
    return valid_results


def synthetic_cost_snapshot(
    idx: int,
    *,
    price: float,
    unit_cost: float,
    margin: float | None = None,
    symbol: str = "RB",
    p25: float = 90.0,
    p50: float = 100.0,
    p75: float = 110.0,
    p90: float = 120.0,
) -> CostSnapshotPoint:
    observed_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=idx)
    return CostSnapshotPoint(
        symbol=symbol,
        timestamp=observed_at,
        current_price=price,
        total_unit_cost=unit_cost,
        breakeven_p25=p25,
        breakeven_p50=p50,
        breakeven_p75=p75,
        breakeven_p90=p90,
        profit_margin=margin,
    )


def synthetic_rubber_news_event(
    event_id: str,
    title: str,
    summary: str,
) -> NewsEventPoint:
    return NewsEventPoint(
        id=event_id,
        source="phase7b_historical_validation",
        title=title,
        summary=summary,
        published_at=datetime(2026, 5, 3, tzinfo=timezone.utc),
        event_type="supply",
        affected_symbols=["NR", "RU"],
        direction="bullish",
        severity=4,
        time_horizon="short",
        confidence=0.8,
        source_count=2,
        verification_status="cross_verified",
    )


def build_quality_report(
    *,
    sector: str = "ferrous",
    comparisons: list[BenchmarkComparison],
    signal_cases: list[SignalCaseResult],
    limitations: list[str] | None = None,
) -> CostQualityReport:
    errors = [item.error_pct for item in comparisons]
    benchmark_passes = [item.within_tolerance for item in comparisons]
    signal_passes = [item.passed for item in signal_cases]
    avg_error = sum(errors) / len(errors) if errors else 100.0
    max_error = max(errors) if errors else 100.0
    benchmark_pass_rate = sum(benchmark_passes) / len(benchmark_passes) if benchmark_passes else 0.0
    signal_hit_rate = sum(signal_passes) / len(signal_passes) if signal_passes else 0.0
    score = quality_score(avg_error, benchmark_pass_rate, signal_hit_rate)
    recommendation, vendor = data_purchase_recommendation(
        benchmark_error_avg_pct=avg_error,
        signal_case_hit_rate=signal_hit_rate,
    )
    return CostQualityReport(
        sector=sector,
        generated_at=datetime.now(timezone.utc),
        benchmark_error_avg_pct=avg_error,
        benchmark_error_max_pct=max_error,
        benchmark_pass_rate=benchmark_pass_rate,
        signal_case_hit_rate=signal_hit_rate,
        data_quality_score=score,
        paid_data_recommendation=recommendation,
        preferred_vendor=vendor,
        benchmark_comparisons=comparisons,
        signal_cases=signal_cases,
        limitations=limitations or [],
    )


def quality_score(
    avg_error_pct: float,
    benchmark_pass_rate: float,
    signal_case_hit_rate: float,
) -> int:
    error_component = max(0.0, 1.0 - avg_error_pct / ACCEPTABLE_BENCHMARK_ERROR_PCT)
    score = error_component * 45 + benchmark_pass_rate * 30 + signal_case_hit_rate * 25
    return round(score)


def data_purchase_recommendation(
    *,
    benchmark_error_avg_pct: float,
    signal_case_hit_rate: float,
) -> tuple[str, str | None]:
    if (
        benchmark_error_avg_pct <= ACCEPTABLE_BENCHMARK_ERROR_PCT
        and signal_case_hit_rate >= MIN_SIGNAL_CASE_HIT_RATE
    ):
        return (
            "defer_paid_purchase_monitor_weekly",
            None,
        )
    if signal_case_hit_rate < MIN_SIGNAL_CASE_HIT_RATE:
        return ("buy_paid_feed_before_expanding_signals", "Mysteel")
    return ("buy_paid_feed_for_precision", "SMM")
