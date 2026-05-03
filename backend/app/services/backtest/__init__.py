"""Backtest correctness guards for PIT replay, multiple testing, and execution realism."""

from app.services.backtest.calibration_replay import (
    CalibrationReplayMetadata,
    calibration_metadata,
    replay_calibration_weight,
)
from app.services.backtest.live_divergence import (
    DivergenceResult,
    algorithm_drift_divergence,
    record_live_divergence,
    sharpe_divergence,
    tracking_error_divergence,
)
from app.services.backtest.multiple_testing import (
    DeflatedSharpeResult,
    benjamini_hochberg_fdr,
    bonferroni_correction,
    deflated_sharpe_ratio,
    sharpe_ratio,
)
from app.services.backtest.path_metrics import PathMetrics, calculate_path_metrics
from app.services.backtest.regime_profile import (
    RegimeObservation,
    RegimeProfileSlice,
    build_regime_profile,
)
from app.services.backtest.slippage import SlippageEstimate, calculate_slippage
from app.services.backtest.strategy_registry import (
    build_strategy_run,
    record_strategy_run,
    stable_strategy_hash,
)
from app.services.backtest.universe import (
    UniverseValidation,
    pit_commodity_universe,
    validate_backtest_universe,
    validate_backtest_universe_from_symbols,
)
from app.services.backtest.walk_forward import (
    WalkForwardWindow,
    generate_walk_forward_windows,
    walk_forward_defaults,
)

__all__ = [
    "CalibrationReplayMetadata",
    "DeflatedSharpeResult",
    "DivergenceResult",
    "PathMetrics",
    "RegimeObservation",
    "RegimeProfileSlice",
    "SlippageEstimate",
    "UniverseValidation",
    "WalkForwardWindow",
    "algorithm_drift_divergence",
    "benjamini_hochberg_fdr",
    "bonferroni_correction",
    "build_strategy_run",
    "calculate_slippage",
    "calculate_path_metrics",
    "calibration_metadata",
    "deflated_sharpe_ratio",
    "generate_walk_forward_windows",
    "build_regime_profile",
    "pit_commodity_universe",
    "record_live_divergence",
    "record_strategy_run",
    "replay_calibration_weight",
    "sharpe_divergence",
    "sharpe_ratio",
    "stable_strategy_hash",
    "tracking_error_divergence",
    "validate_backtest_universe",
    "validate_backtest_universe_from_symbols",
    "walk_forward_defaults",
]
