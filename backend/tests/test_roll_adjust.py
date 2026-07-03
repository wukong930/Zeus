from datetime import date

import pytest

from app.services.backtest.roll_adjust import (
    ContractBar,
    back_adjusted_closes,
    raw_continuous_closes,
)


def _roll_dataset() -> list[ContractBar]:
    # Contract A is dominant on day 1; B takes over (a roll) on day 2 at a much
    # higher price level (a +21% gap in the raw stitch).
    return [
        ContractBar("A", date(2020, 1, 1), 100.0, 1000),
        ContractBar("B", date(2020, 1, 1), 120.0, 10),
        ContractBar("A", date(2020, 1, 2), 101.0, 900),
        ContractBar("B", date(2020, 1, 2), 121.0, 2000),  # B becomes dominant
        ContractBar("B", date(2020, 1, 3), 122.0, 3000),
    ]


def test_raw_continuous_keeps_the_roll_gap():
    closes = raw_continuous_closes(_roll_dataset())
    assert [round(c, 2) for _, c in closes] == [100.0, 121.0, 122.0]
    # the day-2 stitch jumps ~21% — the spurious roll gap
    assert closes[1][1] / closes[0][1] == pytest.approx(1.21)


def test_back_adjusted_removes_the_roll_gap():
    closes = back_adjusted_closes(_roll_dataset(), base=100.0)
    # day 2 uses B's OWN return (121/120 ~ +0.83%), not the 100->121 gap
    assert closes[1][1] / closes[0][1] == pytest.approx(121 / 120)
    # day 3 continues with B's return 122/121
    assert closes[2][1] / closes[1][1] == pytest.approx(122 / 121)
    # no single-day jump anywhere near the 21% roll gap
    rets = [closes[i][1] / closes[i - 1][1] for i in range(1, len(closes))]
    assert max(abs(r - 1) for r in rets) < 0.02
