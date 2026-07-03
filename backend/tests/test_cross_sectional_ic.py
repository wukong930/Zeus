import pytest

from app.services.backtest.cross_sectional_ic import (
    aggregate_ic,
    daily_cross_sectional_ic,
    spearman,
)


def test_spearman_monotonic_relationships():
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 2], [1, 2]) is None  # too few points
    assert spearman([1, 1, 1], [1, 2, 3]) is None  # zero variance


def test_spearman_handles_ties():
    value = spearman([1.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    assert value is not None
    assert 0.0 < value < 1.0


def test_daily_cross_sectional_ic_ranks_symbols():
    feature = {"A": 3.0, "B": 2.0, "C": 1.0}
    aligned = {"A": 0.05, "B": 0.02, "C": -0.01}
    assert daily_cross_sectional_ic(feature, aligned) == pytest.approx(1.0)

    reversed_fwd = {"A": -0.05, "B": 0.0, "C": 0.05}
    assert daily_cross_sectional_ic(feature, reversed_fwd) == pytest.approx(-1.0)

    # fewer than 3 overlapping symbols -> undefined
    assert daily_cross_sectional_ic({"A": 1.0}, {"A": 1.0}) is None
    # None values are skipped
    assert daily_cross_sectional_ic({"A": 1.0, "B": None, "C": 3.0}, {"A": 1.0, "C": 3.0}) is None


def test_aggregate_ic_computes_tstat_and_positivity():
    flat = aggregate_ic("mom_60", 20, [0.05, 0.05, 0.05, 0.05])
    assert flat.n_days == 4
    assert flat.mean_ic == pytest.approx(0.05)
    assert flat.t_stat == 0.0  # zero variance guard
    assert flat.is_significant is False

    mixed = aggregate_ic("mom_60", 20, [0.1, 0.0, 0.2, -0.1, 0.1, None])
    assert mixed.n_days == 5  # None skipped
    assert mixed.mean_ic == pytest.approx(0.06)
    assert mixed.pct_positive == pytest.approx(3 / 5)


def test_aggregate_ic_significant_factor():
    # a steady IC of ~0.04 over many days with low noise -> high t-stat, significant
    daily = [0.04, 0.05, 0.03, 0.04, 0.05, 0.03] * 50
    result = aggregate_ic("mom_60", 20, daily)
    assert result.mean_ic == pytest.approx(0.04, abs=0.005)
    assert result.t_stat > 3.0
    assert result.is_significant is True
