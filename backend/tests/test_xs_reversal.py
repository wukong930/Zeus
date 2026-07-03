import pytest

from app.services.backtest.multiple_testing import DeflatedSharpeResult
from app.services.backtest.xs_reversal import (
    gross_period_return,
    one_way_turnover,
    run_xs_backtest,
    select_long_short,
)


def test_select_long_short_picks_losers_long_winners_short():
    signal = {"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0, "F": 6.0}
    long, short = select_long_short(signal, k=2)
    assert long == ("A", "B")  # lowest momentum (losers) -> long
    assert short == ("E", "F")  # highest momentum (winners) -> short


def test_select_long_short_needs_enough_symbols():
    assert select_long_short({"A": 1.0, "B": 2.0, "C": 3.0}, k=2) == ((), ())
    # None / non-finite values are excluded
    assert select_long_short({"A": 1.0, "B": None, "C": float("nan")}, k=2) == ((), ())


def test_gross_period_return_is_long_losers_minus_short_winners():
    long, short = ("A", "B"), ("E", "F")
    forward = {"A": 0.05, "B": 0.03, "E": -0.02, "F": -0.04}
    # long mean 0.04, short mean -0.03 -> reversal pays 0.07
    assert gross_period_return(long, short, forward) == pytest.approx(0.07)


def test_leg_mean_clips_roll_artifacts():
    # the +3.0 (300%) is a roll artifact -> excluded; leg uses the other member
    long, short = ("A", "B"), ("E", "F")
    forward = {"A": 3.0, "B": 0.02, "E": -0.01, "F": -0.03}
    # long mean uses only B (0.02); short mean = -0.02 -> 0.04
    assert gross_period_return(long, short, forward) == pytest.approx(0.04)


def test_one_way_turnover():
    assert one_way_turnover(set(), {"A", "B"}) == pytest.approx(1.0)
    assert one_way_turnover({"A", "B"}, {"A", "B"}) == pytest.approx(0.0)
    assert one_way_turnover({"A", "B"}, {"B", "C"}) == pytest.approx(0.5)


def test_run_xs_backtest_nets_turnover_cost_and_reports():
    gross = [0.02, 0.03, 0.01, 0.04]
    turnovers = [0.5, 0.5, 0.5, 0.5]
    report = run_xs_backtest(
        "mom_60", gross, turnovers, quantile_k=5, cost_bps=10.0, periods_per_year=12, trials=4
    )
    assert report.periods == 4
    assert report.gross_mean_return == pytest.approx(0.025)
    # net = gross - 0.5 * 0.001 = gross - 0.0005
    assert report.net_mean_return == pytest.approx(0.0245)
    assert report.win_rate == pytest.approx(1.0)
    assert report.avg_turnover == pytest.approx(0.5)
    assert isinstance(report.deflated, DeflatedSharpeResult)
    assert report.deflated.trials == 4
    assert isinstance(report.has_significant_edge, bool)
