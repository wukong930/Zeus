from datetime import datetime, timedelta, timezone

import pytest

from app.services.backtest.multiple_testing import DeflatedSharpeResult
from app.services.backtest.spread_replay import (
    SpreadTrade,
    aligned_log_spread,
    detect_spread_trades,
    rolling_zscores,
    run_spread_backtest,
)
from app.services.signals.types import MarketBar

_BASE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _bar(day: int, close: float) -> MarketBar:
    return MarketBar(
        timestamp=_BASE + timedelta(days=day),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
    )


def test_aligned_log_spread_uses_common_days_only():
    import math

    bars1 = [_bar(0, 100), _bar(1, 110), _bar(2, 120)]
    bars2 = [_bar(1, 100), _bar(2, 100)]  # day 0 missing for leg2
    dates, spread = aligned_log_spread(bars1, bars2)

    assert len(dates) == 2  # only days 1 and 2 are common
    assert spread[0] == pytest.approx(math.log(110 / 100))
    assert spread[1] == pytest.approx(math.log(120 / 100))


def test_rolling_zscores_are_point_in_time():
    z = rolling_zscores([1.0, 1.0, 1.0, 3.0], window=2)
    assert z[0] is None  # not enough history
    assert z[1] is None  # std == 0
    assert z[2] is None  # std == 0
    assert z[3] == pytest.approx(1.0)  # window [1,3]: mean 2, std 1 -> (3-2)/1


def test_detect_spread_trades_shorts_a_rich_spread():
    dates = [_BASE + timedelta(days=d) for d in range(7)]
    spread = [0.0, 0.0, 0.01, 0.02, 0.05, 0.04, 0.03]
    zscores = [None, None, 1.0, 2.5, 1.0, 0.0, 0.0]  # crosses above +2 at index 3

    trades = detect_spread_trades("RB-HC", dates, spread, zscores, entry_z=2.0)

    assert len(trades) == 1
    trade = trades[0]
    assert trade.bet_sign == -1  # short the rich spread
    assert trade.entry_z == pytest.approx(2.5)
    assert trade.forward_spread_return[1] == pytest.approx(0.03)  # spread[4] - spread[3]


def test_detect_spread_trades_drop_roll_artifact_forward_returns():
    dates = [_BASE + timedelta(days=d) for d in range(4)]
    spread = [0.0, 0.0, 0.01, 5.0]  # index 3 is a ~5.0 contract-roll jump
    zscores = [None, 1.0, 2.5, 0.0]  # crosses above +2 at index 2

    trades = detect_spread_trades("RB-HC", dates, spread, zscores, entry_z=2.0)

    assert len(trades) == 1
    # forward[1] = spread[3] - spread[2] ~= 5.0 -> dropped as a roll artifact
    assert trades[0].forward_spread_return[1] is None


def test_detect_spread_trades_longs_a_cheap_spread():
    dates = [_BASE + timedelta(days=d) for d in range(5)]
    spread = [0.0, 0.0, -1.0, -2.0, -3.0]
    zscores = [None, None, -1.0, -2.5, -1.0]  # crosses below -2 at index 3

    trades = detect_spread_trades("RB-HC", dates, spread, zscores, entry_z=2.0)

    assert len(trades) == 1
    assert trades[0].bet_sign == 1  # long the cheap spread


def _trade(pair: str, fwd5: float | None, bet_sign: int = -1) -> SpreadTrade:
    return SpreadTrade(
        pair=pair,
        entry_date=_BASE,
        entry_z=2.5,
        bet_sign=bet_sign,
        forward_spread_return={1: None, 5: fwd5, 20: None},
    )


def test_run_spread_backtest_nets_two_leg_cost_and_reports_edge():
    # bet_sign -1 with negative forward (spread reverted down) -> profitable
    trades = {
        "RB-HC": [_trade("RB-HC", -0.03), _trade("RB-HC", -0.02), _trade("RB-HC", 0.01)],
        "CU-AL": [_trade("CU-AL", -0.01), _trade("CU-AL", 0.02)],
    }
    report = run_spread_backtest(trades, horizon=5, round_trip_cost_bps=4.0)

    assert report.total_trades == 5
    assert report.round_trip_cost_bps == 4.0
    # RB-HC: net = -bet*fwd... bet_sign=-1 -> net = (-1)*fwd - cost
    #   fwd -0.03 -> +0.03 - 0.0004 = 0.0296 (win); -0.02 -> 0.0196 (win); 0.01 -> -0.0104 (loss)
    rb = next(e for e in report.per_pair if e.pair == "RB-HC")
    assert rb.trades == 3
    assert rb.win_rate == pytest.approx(2 / 3)
    assert rb.mean_net_return == pytest.approx((0.0296 + 0.0196 - 0.0104) / 3)
    assert isinstance(report.portfolio_deflated, DeflatedSharpeResult)
    assert report.portfolio_deflated.trials == 2  # two pairs
    assert isinstance(report.has_significant_edge, bool)
