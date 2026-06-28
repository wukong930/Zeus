from datetime import datetime, timedelta, timezone

import pytest

from app.services.backtest.walk_forward_xs import (
    sub_period_breakdown,
    walk_forward_oos,
)

_BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _dates(n: int) -> list[datetime]:
    return [_BASE + timedelta(days=30 * i) for i in range(n)]


def test_sub_period_breakdown_splits_into_blocks():
    days = _dates(12)
    returns = [0.01] * 4 + [0.02] * 4 + [0.03] * 4
    dated = list(zip(days, returns, strict=True))

    blocks = sub_period_breakdown(dated, n_blocks=3, periods_per_year=12)

    assert len(blocks) == 3
    assert blocks[0].mean_return == pytest.approx(0.01)
    assert blocks[1].mean_return == pytest.approx(0.02)
    assert blocks[2].mean_return == pytest.approx(0.03)
    assert all(block.win_rate == pytest.approx(1.0) for block in blocks)


def test_walk_forward_selects_best_signal_on_train_and_applies_to_test():
    days = _dates(12)
    # signal A is the consistent winner; B loses -> A must be picked every window
    a = [0.01 if i % 2 == 0 else 0.03 for i in range(12)]
    b = [-0.03 if i % 2 == 0 else -0.01 for i in range(12)]
    returns_by_signal = {
        "A": list(zip(days, a, strict=True)),
        "B": list(zip(days, b, strict=True)),
    }

    result = walk_forward_oos(returns_by_signal, train=4, test=2, periods_per_year=12)

    # test windows cover periods 4..11 -> 8 out-of-sample periods
    assert result.oos_periods == 8
    assert all(signal == "A" for _, signal in result.selections)
    assert result.oos_mean_return == pytest.approx(0.02)
    assert result.oos_win_rate == pytest.approx(1.0)


def test_walk_forward_empty_input():
    result = walk_forward_oos({}, train=4, test=2, periods_per_year=12)
    assert result.oos_periods == 0
    assert result.has_significant_edge is False
