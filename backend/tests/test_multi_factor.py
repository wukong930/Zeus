import statistics

import pytest

from app.services.backtest.multi_factor import composite_score, cross_sectional_zscore


def test_cross_sectional_zscore_normalizes():
    z = cross_sectional_zscore({"A": 0.0, "B": 2.0, "C": 4.0})
    assert sum(z.values()) == pytest.approx(0.0)
    assert z["C"] > z["B"] > z["A"]
    assert statistics.pstdev(z.values()) == pytest.approx(1.0)


def test_cross_sectional_zscore_edge_cases():
    assert cross_sectional_zscore({"A": 5.0, "B": 5.0}) == {"A": 0.0, "B": 0.0}  # zero variance
    assert cross_sectional_zscore({"A": 1.0}) == {}  # too few
    assert cross_sectional_zscore({"A": 1.0, "B": None, "C": float("nan")}) == {}  # < 2 valid


def test_composite_score_combines_and_cancels():
    # two perfectly-opposed factors cancel to ~0
    factors = {
        "f1": {"A": 0.0, "B": 2.0, "C": 4.0},
        "f2": {"A": 4.0, "B": 2.0, "C": 0.0},
    }
    composite = composite_score(factors)
    assert composite["A"] == pytest.approx(0.0)
    assert composite["B"] == pytest.approx(0.0)
    assert composite["C"] == pytest.approx(0.0)


def test_composite_score_respects_weights():
    factors = {
        "f1": {"A": 0.0, "B": 2.0, "C": 4.0},
        "f2": {"A": 4.0, "B": 2.0, "C": 0.0},
    }
    # weight only f1 -> follows f1 ordering
    composite = composite_score(factors, weights={"f1": 1.0, "f2": 0.0})
    assert composite["C"] > composite["B"] > composite["A"]
