from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services.backtest.multiple_testing import DeflatedSharpeResult
from app.services.backtest.signal_backtest import (
    BacktestSignal,
    _backtest_signals_statement,
    classify_semantics,
    default_round_trip_cost_bps,
    load_backtest_signals,
    net_directional_return,
    run_signal_backtest,
)


def _momentum_dataset() -> list[BacktestSignal]:
    # net (cost=2bps=0.0002): 0.0198, 0.0098, 0.0298, -0.0102 -> mean 0.0123
    return [
        BacktestSignal("momentum", "bullish", "hit", forward_return_5d=0.02),
        BacktestSignal("momentum", "bullish", "hit", forward_return_5d=0.01),
        BacktestSignal("momentum", "bearish", "hit", forward_return_5d=-0.03),
        BacktestSignal("momentum", "bullish", "miss", forward_return_5d=-0.01),
    ]


def test_semantics_classification_matches_evaluator_outcome_functions():
    assert classify_semantics("momentum") == "directional"
    assert classify_semantics("basis_shift") == "directional"
    assert classify_semantics("capacity_contraction") == "directional"
    assert classify_semantics("spread_anomaly") == "mean_reversion"
    assert classify_semantics("regime_shift") == "volatility"
    assert classify_semantics("inventory_shock") == "volatility"
    assert classify_semantics("not_a_real_signal") == "unknown"


def test_default_cost_is_sourced_from_slippage_model_not_a_magic_number():
    # round-trip floor = 2 x main-tier base (1.0 bps)
    assert default_round_trip_cost_bps() == 2.0


def test_net_directional_return_nets_cost_and_respects_direction():
    assert net_directional_return(0.02, "bullish", round_trip_cost=0.0002) == pytest.approx(0.0198)
    assert net_directional_return(-0.03, "bearish", round_trip_cost=0.0002) == pytest.approx(0.0298)
    # unknown direction is untradable -> excluded, not treated as flat
    assert net_directional_return(0.02, None, round_trip_cost=0.0002) is None


def test_directional_portfolio_math_is_exact():
    report = run_signal_backtest(_momentum_dataset(), horizon=5)

    assert report.directional_trades == 4
    assert report.portfolio_gross_accuracy == pytest.approx(0.75)
    assert report.portfolio_cost_aware_hit_rate == pytest.approx(0.75)
    assert report.portfolio_mean_net_return == pytest.approx(0.0123)
    assert report.round_trip_cost_bps == 2.0

    momentum = next(e for e in report.per_signal if e.signal_type == "momentum")
    assert momentum.semantics == "directional"
    assert momentum.scored_trades == 4
    assert momentum.gross_directional_accuracy == pytest.approx(0.75)
    assert momentum.cost_aware_hit_rate == pytest.approx(0.75)
    assert momentum.mean_net_return == pytest.approx(0.0123)
    assert momentum.stored_hit_rate == pytest.approx(0.75)


def test_hit_rate_is_reported_split_by_semantics_not_mushed_together():
    signals = [
        *_momentum_dataset(),  # directional: 3 hit / 4 resolved
        BacktestSignal("spread_anomaly", None, "hit"),
        BacktestSignal("spread_anomaly", None, "hit"),
        BacktestSignal("spread_anomaly", None, "miss"),  # mean_reversion: 2/3
        BacktestSignal("regime_shift", None, "hit"),
        BacktestSignal("regime_shift", None, "miss"),  # volatility: 1/2
    ]
    report = run_signal_backtest(signals, horizon=5)

    assert report.count_by_class == {"directional": 4, "mean_reversion": 3, "volatility": 2}
    assert report.hit_rate_by_class["directional"] == pytest.approx(0.75)
    assert report.hit_rate_by_class["mean_reversion"] == pytest.approx(2 / 3)
    assert report.hit_rate_by_class["volatility"] == pytest.approx(0.5)

    # non-directional signals never produce a directional edge (category error guard)
    spread = next(e for e in report.per_signal if e.signal_type == "spread_anomaly")
    assert spread.semantics == "mean_reversion"
    assert spread.cost_aware_hit_rate is None
    assert spread.mean_net_return is None
    assert spread.deflated is None
    assert spread.stored_hit_rate == pytest.approx(2 / 3)

    # non-directional signals are excluded from the tradable directional portfolio
    assert report.directional_trades == 4


def test_deflated_sharpe_gate_and_fdr_wired_across_directional_families():
    signals = [
        BacktestSignal("momentum", "bullish", "hit", forward_return_5d=0.02),
        BacktestSignal("momentum", "bullish", "hit", forward_return_5d=0.015),
        BacktestSignal("momentum", "bearish", "hit", forward_return_5d=-0.02),
        BacktestSignal("price_gap", "bullish", "hit", forward_return_5d=0.03),
        BacktestSignal("price_gap", "bullish", "miss", forward_return_5d=-0.01),
        BacktestSignal("price_gap", "bearish", "hit", forward_return_5d=-0.025),
    ]
    report = run_signal_backtest(signals, horizon=5)

    assert isinstance(report.portfolio_deflated, DeflatedSharpeResult)
    # two directional families were data-snooped -> deflation must account for it
    assert report.portfolio_deflated.trials == 2
    assert isinstance(report.has_significant_edge, bool)
    assert report.portfolio_path is not None

    directional_edges = [e for e in report.per_signal if e.semantics == "directional"]
    assert len(directional_edges) == 2
    for edge in directional_edges:
        assert edge.deflated is not None
        assert edge.deflated.trials == 2
        assert edge.fdr_rejected is not None  # FDR decision grafted back
        assert edge.fdr_adjusted_pvalue is not None


def test_empty_input_is_handled_without_a_portfolio():
    report = run_signal_backtest([], horizon=5)
    assert report.total_signals == 0
    assert report.directional_trades == 0
    assert report.portfolio_deflated is None
    assert report.has_significant_edge is False
    assert report.to_dict()["portfolio_mean_net_return"] is None


def test_loader_statement_excludes_pending_and_uses_stable_order():
    sql = str(
        _backtest_signals_statement(limit=100).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "signal_track.outcome != 'pending'" in sql
    assert "order by signal_track.created_at asc, signal_track.id asc" in sql
    assert "limit 100" in sql


def test_loader_statement_supports_keyset_cursor():
    sql = str(
        _backtest_signals_statement(
            before=datetime(2026, 5, 1, tzinfo=timezone.utc),
            before_id=__import__("uuid").uuid4(),
            limit=50,
        ).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    ).lower()
    assert "signal_track.created_at <" in sql
    assert "signal_track.id <" in sql


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.captured = None

    async def scalars(self, statement):
        self.captured = statement
        return _FakeScalars(self._rows)


async def test_load_backtest_signals_maps_rows_to_dataclass():
    created = datetime(2026, 5, 18, tzinfo=timezone.utc)
    rows = [
        SimpleNamespace(
            signal_type="momentum",
            direction="bullish",
            outcome="hit",
            forward_return_1d=None,
            forward_return_5d=0.02,
            forward_return_20d=0.05,
            created_at=created,
        )
    ]
    session = _FakeSession(rows)

    result = await load_backtest_signals(session)

    assert result == [
        BacktestSignal(
            signal_type="momentum",
            direction="bullish",
            outcome="hit",
            forward_return_1d=None,
            forward_return_5d=0.02,
            forward_return_20d=0.05,
            created_at=created,
        )
    ]
    assert session.captured is not None
