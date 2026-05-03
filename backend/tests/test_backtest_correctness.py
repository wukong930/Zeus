from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.change_review_queue import ChangeReviewQueue
from app.models.live_divergence_metrics import LiveDivergenceMetric
from app.services.backtest.calibration_replay import (
    CURRENT_WARNING,
    calibration_metadata,
    replay_calibration_weight,
)
from app.services.backtest.live_divergence import (
    record_live_divergence,
    sharpe_divergence,
    tracking_error_divergence,
)
from app.services.backtest.multiple_testing import (
    benjamini_hochberg_fdr,
    bonferroni_correction,
    deflated_sharpe_ratio,
)
from app.services.backtest.slippage import calculate_slippage
from app.services.backtest.strategy_registry import build_strategy_run, stable_strategy_hash
from app.services.backtest.walk_forward import (
    generate_walk_forward_windows,
    walk_forward_defaults,
)


class FakeSession:
    def __init__(self) -> None:
        self.rows: list[object] = []
        self.flush_count = 0

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


async def test_replay_calibration_weight_uses_point_in_time_lookup() -> None:
    calls: list[datetime] = []
    signal_time = datetime(2025, 9, 1, tzinfo=timezone.utc)
    backtest_start = datetime(2025, 1, 1, tzinfo=timezone.utc)

    async def fake_loader(_session, **kwargs) -> float:
        calls.append(kwargs["as_of"])
        return 1.23

    weight, metadata = await replay_calibration_weight(
        None,
        signal_type="momentum",
        category="ferrous",
        regime="range_low_vol",
        signal_time=signal_time,
        backtest_start=backtest_start,
        strategy="pit",
        loader=fake_loader,
    )

    assert weight == 1.23
    assert calls == [signal_time]
    assert metadata.warning is None


def test_current_calibration_strategy_is_marked_not_decision_grade() -> None:
    current_time = datetime(2026, 5, 4, tzinfo=timezone.utc)

    metadata = calibration_metadata(
        strategy="current",
        signal_time=datetime(2025, 9, 1, tzinfo=timezone.utc),
        backtest_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        current_time=current_time,
    )

    assert metadata.lookup_time == current_time
    assert metadata.warning == CURRENT_WARNING
    assert metadata.to_dict()["decision_grade"] is False


def test_deflated_sharpe_rejects_multiple_testing_luck() -> None:
    result = deflated_sharpe_ratio(raw_sharpe=0.4, returns_count=252, trials=100)

    assert result.raw_sharpe == 0.4
    assert result.passed_gate is False
    assert result.deflated_pvalue > 0.05


def test_deflated_sharpe_can_pass_strong_strategy() -> None:
    result = deflated_sharpe_ratio(raw_sharpe=5.0, returns_count=504, trials=3)

    assert result.deflated_sharpe > 1.0
    assert result.deflated_pvalue < 0.05
    assert result.passed_gate is True


def test_strategy_run_registry_records_deflated_gate_and_current_warning() -> None:
    params = {"lookback": 20, "threshold": 2.0}
    data_start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    data_end = datetime(2026, 1, 1, tzinfo=timezone.utc)

    row = build_strategy_run(
        strategy_name="spread-revert",
        strategy_space="spread",
        params=params,
        data_start=data_start,
        data_end=data_end,
        raw_sharpe=5.0,
        returns_count=504,
        trials=3,
        calibration_strategy="current",
    )

    assert row.strategy_hash == stable_strategy_hash(
        strategy_name="spread-revert",
        strategy_space="spread",
        params=params,
    )
    assert row.calibration_strategy == "current"
    assert row.result_warning is not None
    assert row.passed_gate is False
    assert row.metrics["multiple_testing"]["passed_gate"] is True


def test_fdr_and_bonferroni_adjust_multiple_pvalues() -> None:
    pvalues = [0.001, 0.02, 0.04, 0.2]

    fdr = benjamini_hochberg_fdr(pvalues)
    bonferroni = bonferroni_correction(pvalues)

    assert [item.rejected for item in fdr] == [True, True, False, False]
    assert [round(item.adjusted_pvalue, 3) for item in bonferroni] == [0.004, 0.08, 0.16, 0.8]


def test_slippage_model_distinguishes_main_and_third_contracts() -> None:
    timestamp = datetime(2026, 5, 4, 10, 0, tzinfo=timezone.utc)

    main = calculate_slippage(
        symbol="RB",
        contract_tier="main",
        atr_percentile=0.5,
        order_size=5_000,
        average_daily_volume=1_000_000,
        timestamp=timestamp,
    )
    third = calculate_slippage(
        symbol="RB",
        contract_tier="third",
        atr_percentile=0.5,
        order_size=5_000,
        average_daily_volume=1_000_000,
        timestamp=timestamp,
    )

    assert main.executable is True
    assert third.slippage_bps is not None and main.slippage_bps is not None
    assert third.slippage_bps == main.slippage_bps * 8


def test_slippage_delivery_and_limit_lock_rules() -> None:
    timestamp = datetime(2026, 5, 4, 9, 5, tzinfo=timezone.utc)

    delivery = calculate_slippage(
        symbol="RB",
        contract_tier="main",
        atr_percentile=0.8,
        order_size=60_000,
        average_daily_volume=1_000_000,
        timestamp=timestamp,
        days_to_delivery=7,
    )
    locked = calculate_slippage(
        symbol="RB",
        contract_tier="main",
        atr_percentile=0.8,
        order_size=60_000,
        average_daily_volume=1_000_000,
        timestamp=timestamp,
        limit_locked=True,
    )

    assert delivery.delivery_multiplier_applied is True
    assert delivery.recommended_contract_shift is True
    assert delivery.slippage_bps == 1.0 * 1.8 * 2.5 * 1.5 * 3
    assert locked.executable is False
    assert locked.slippage_bps is None


def test_live_divergence_detects_tracking_and_sharpe_breaks() -> None:
    tracking = tracking_error_divergence([0.01, 0.0, -0.005], [-0.02, 0.015, -0.03], threshold=0.01)
    sharpe = sharpe_divergence(
        backtest_sharpe=1.5,
        backtest_sharpe_std=0.4,
        live_sharpe=0.1,
        live_sample_size=64,
    )

    assert tracking.severity == "red"
    assert sharpe.severity == "red"
    assert sharpe.triggered is True


async def test_record_live_divergence_queues_review_for_red_metric() -> None:
    session = FakeSession()
    result = sharpe_divergence(
        backtest_sharpe=1.5,
        backtest_sharpe_std=0.4,
        live_sharpe=0.1,
        live_sample_size=64,
    )

    row = await record_live_divergence(
        session,  # type: ignore[arg-type]
        strategy_hash="strategy-a",
        result=result,
    )

    assert isinstance(row, LiveDivergenceMetric)
    assert isinstance(session.rows[1], ChangeReviewQueue)
    assert session.rows[1].target_key == "strategy-a"
    assert session.flush_count == 1


def test_walk_forward_defaults_generate_reproducible_windows() -> None:
    windows = generate_walk_forward_windows(
        start=date(2020, 1, 1),
        end=date(2023, 7, 1),
    )

    assert walk_forward_defaults() == {
        "training_years": 3,
        "test_months": 3,
        "step_months": 1,
        "mode": "rolling",
    }
    assert windows[0].train_start == date(2020, 1, 1)
    assert windows[0].test_start == date(2023, 1, 1)
    assert windows[0].test_end == date(2023, 4, 1)
    assert windows[-1].test_end == date(2023, 7, 1)
