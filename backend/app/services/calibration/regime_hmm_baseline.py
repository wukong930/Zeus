from __future__ import annotations

from dataclasses import dataclass
from math import log, pi

import numpy as np

from app.services.calibration.regime_detector import (
    REGIME_RANGE_HIGH_VOL,
    REGIME_RANGE_LOW_VOL,
    REGIME_TREND_DOWN_LOW_VOL,
    REGIME_TREND_UP_LOW_VOL,
    detect_regime,
)
from app.services.signals.types import MarketBar

EPSILON = 1e-9
DEFAULT_HMM_STATES = 4
MIN_HMM_FEATURES = 30


@dataclass(frozen=True)
class HMMFeature:
    timestamp: str
    return_pct: float
    range_pct: float
    volume_change_pct: float


@dataclass(frozen=True)
class HMMStateSummary:
    state: int
    regime: str
    sample_size: int
    mean_return_pct: float
    mean_range_pct: float
    mean_volume_change_pct: float
    persistence: float


@dataclass(frozen=True)
class HMMRegimeObservation:
    timestamp: str
    state: int
    hmm_regime: str
    rule_regime: str | None


@dataclass(frozen=True)
class HMMRegimeBaselineReport:
    status: str
    sample_size: int
    feature_count: int
    states: int
    latest_hmm_regime: str | None
    latest_rule_regime: str | None
    agreement_rate: float | None
    state_summaries: list[HMMStateSummary]
    observations: list[HMMRegimeObservation]
    note: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "sample_size": self.sample_size,
            "feature_count": self.feature_count,
            "states": self.states,
            "latest_hmm_regime": self.latest_hmm_regime,
            "latest_rule_regime": self.latest_rule_regime,
            "agreement_rate": self.agreement_rate,
            "state_summaries": [summary.__dict__ for summary in self.state_summaries],
            "observations": [observation.__dict__ for observation in self.observations],
            "note": self.note,
        }


def run_hmm_regime_baseline(
    bars: list[MarketBar],
    *,
    states: int = DEFAULT_HMM_STATES,
    min_features: int = MIN_HMM_FEATURES,
    iterations: int = 8,
    rule_period: int = 14,
    observation_tail: int = 40,
) -> HMMRegimeBaselineReport:
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    features = market_bars_to_hmm_features(ordered)
    bounded_states = max(2, min(int(states), 6))
    if len(features) < min_features:
        latest_rule = detect_regime(ordered, period=rule_period).regime if ordered else None
        return HMMRegimeBaselineReport(
            status="insufficient_data",
            sample_size=len(ordered),
            feature_count=len(features),
            states=bounded_states,
            latest_hmm_regime=None,
            latest_rule_regime=latest_rule,
            agreement_rate=None,
            state_summaries=[],
            observations=[],
            note="Not enough market features for HMM baseline comparison.",
        )

    matrix = _feature_matrix(features)
    state_path, transition = _fit_gaussian_hmm_viterbi(
        matrix,
        states=bounded_states,
        iterations=iterations,
    )
    regimes_by_state = _state_regime_labels(matrix, state_path, bounded_states)
    rule_regimes = _rolling_rule_regimes(ordered, feature_count=len(features), period=rule_period)
    observations = [
        HMMRegimeObservation(
            timestamp=features[idx].timestamp,
            state=int(state),
            hmm_regime=regimes_by_state[int(state)],
            rule_regime=rule_regimes[idx],
        )
        for idx, state in enumerate(state_path)
    ]
    comparable = [item for item in observations if item.rule_regime is not None]
    agreement_rate = (
        round(
            sum(item.hmm_regime == item.rule_regime for item in comparable) / len(comparable),
            4,
        )
        if comparable
        else None
    )
    summaries = _state_summaries(
        matrix,
        state_path,
        transition,
        regimes_by_state,
        bounded_states,
    )
    latest_hmm = observations[-1].hmm_regime if observations else None
    latest_rule = detect_regime(ordered, period=rule_period).regime
    return HMMRegimeBaselineReport(
        status="completed",
        sample_size=len(ordered),
        feature_count=len(features),
        states=bounded_states,
        latest_hmm_regime=latest_hmm,
        latest_rule_regime=latest_rule,
        agreement_rate=agreement_rate,
        state_summaries=summaries,
        observations=observations[-observation_tail:],
        note="Research baseline only; not used by production regime_state or signal calibration.",
    )


def market_bars_to_hmm_features(bars: list[MarketBar]) -> list[HMMFeature]:
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    features: list[HMMFeature] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        previous_close = max(float(previous.close), EPSILON)
        previous_volume = max(float(previous.volume), EPSILON)
        close = float(current.close)
        range_base = max(close, EPSILON)
        features.append(
            HMMFeature(
                timestamp=current.timestamp.isoformat(),
                return_pct=round(((close - previous_close) / previous_close) * 100, 6),
                range_pct=round(((float(current.high) - float(current.low)) / range_base) * 100, 6),
                volume_change_pct=round(
                    ((float(current.volume) - previous_volume) / previous_volume) * 100,
                    6,
                ),
            )
        )
    return features


def _feature_matrix(features: list[HMMFeature]) -> np.ndarray:
    return np.asarray(
        [
            [feature.return_pct, feature.range_pct, feature.volume_change_pct]
            for feature in features
        ],
        dtype=float,
    )


def _fit_gaussian_hmm_viterbi(
    matrix: np.ndarray,
    *,
    states: int,
    iterations: int,
) -> tuple[np.ndarray, np.ndarray]:
    normalized = _standardize(matrix)
    path = _initial_state_path(matrix, states)
    transition = _transition_matrix(path, states)
    means, variances = _state_gaussians(normalized, path, states)

    for _ in range(max(1, iterations)):
        path = _viterbi_path(normalized, means, variances, transition)
        transition = _transition_matrix(path, states)
        means, variances = _state_gaussians(normalized, path, states)
    return path, transition


def _standardize(matrix: np.ndarray) -> np.ndarray:
    std = matrix.std(axis=0)
    std = np.where(std < EPSILON, 1.0, std)
    return (matrix - matrix.mean(axis=0)) / std


def _initial_state_path(matrix: np.ndarray, states: int) -> np.ndarray:
    vol = np.abs(matrix[:, 0]) + matrix[:, 1]
    trend = matrix[:, 0]
    score = vol + np.where(trend >= 0, 0.1, -0.1)
    quantiles = np.quantile(score, np.linspace(0, 1, states + 1)[1:-1])
    return np.asarray(np.digitize(score, quantiles), dtype=int)


def _transition_matrix(path: np.ndarray, states: int) -> np.ndarray:
    counts = np.full((states, states), 0.1)
    for previous, current in zip(path, path[1:], strict=False):
        counts[int(previous), int(current)] += 1
    return counts / counts.sum(axis=1, keepdims=True)


def _state_gaussians(
    normalized: np.ndarray,
    path: np.ndarray,
    states: int,
) -> tuple[np.ndarray, np.ndarray]:
    global_mean = normalized.mean(axis=0)
    global_var = np.maximum(normalized.var(axis=0), 0.05)
    means = np.zeros((states, normalized.shape[1]))
    variances = np.zeros((states, normalized.shape[1]))
    for state in range(states):
        rows = normalized[path == state]
        if len(rows) == 0:
            means[state] = global_mean
            variances[state] = global_var
            continue
        means[state] = rows.mean(axis=0)
        variances[state] = np.maximum(rows.var(axis=0), 0.05)
    return means, variances


def _viterbi_path(
    normalized: np.ndarray,
    means: np.ndarray,
    variances: np.ndarray,
    transition: np.ndarray,
) -> np.ndarray:
    states = len(means)
    log_transition = np.log(np.maximum(transition, EPSILON))
    log_start = np.full(states, -log(states))
    emissions = np.asarray([_log_gaussian(row, means, variances) for row in normalized])
    scores = np.zeros((len(normalized), states))
    backpointers = np.zeros((len(normalized), states), dtype=int)
    scores[0] = log_start + emissions[0]
    for idx in range(1, len(normalized)):
        for state in range(states):
            candidates = scores[idx - 1] + log_transition[:, state]
            previous = int(np.argmax(candidates))
            scores[idx, state] = candidates[previous] + emissions[idx, state]
            backpointers[idx, state] = previous
    path = np.zeros(len(normalized), dtype=int)
    path[-1] = int(np.argmax(scores[-1]))
    for idx in range(len(normalized) - 2, -1, -1):
        path[idx] = backpointers[idx + 1, path[idx + 1]]
    return path


def _log_gaussian(row: np.ndarray, means: np.ndarray, variances: np.ndarray) -> np.ndarray:
    return -0.5 * (
        np.sum(log(2 * pi) + np.log(variances) + ((row - means) ** 2 / variances), axis=1)
    )


def _state_regime_labels(
    matrix: np.ndarray,
    path: np.ndarray,
    states: int,
) -> dict[int, str]:
    range_values = matrix[:, 1]
    high_vol_cutoff = float(np.percentile(range_values, 65))
    labels: dict[int, str] = {}
    for state in range(states):
        rows = matrix[path == state]
        if len(rows) == 0:
            labels[state] = REGIME_RANGE_LOW_VOL
            continue
        mean_return = float(rows[:, 0].mean())
        mean_range = float(rows[:, 1].mean())
        if abs(mean_return) >= 0.08 and mean_range < high_vol_cutoff:
            labels[state] = REGIME_TREND_UP_LOW_VOL if mean_return > 0 else REGIME_TREND_DOWN_LOW_VOL
        elif mean_range >= high_vol_cutoff:
            labels[state] = REGIME_RANGE_HIGH_VOL
        else:
            labels[state] = REGIME_RANGE_LOW_VOL
    return labels


def _rolling_rule_regimes(
    bars: list[MarketBar],
    *,
    feature_count: int,
    period: int,
) -> list[str | None]:
    regimes: list[str | None] = []
    first_feature_bar_index = len(bars) - feature_count
    for feature_idx in range(feature_count):
        bar_idx = first_feature_bar_index + feature_idx
        window = bars[: bar_idx + 1]
        if len(window) < period + 2:
            regimes.append(None)
        else:
            regimes.append(detect_regime(window, period=period).regime)
    return regimes


def _state_summaries(
    matrix: np.ndarray,
    path: np.ndarray,
    transition: np.ndarray,
    labels: dict[int, str],
    states: int,
) -> list[HMMStateSummary]:
    summaries: list[HMMStateSummary] = []
    for state in range(states):
        rows = matrix[path == state]
        if len(rows) == 0:
            summary = HMMStateSummary(
                state=state,
                regime=labels[state],
                sample_size=0,
                mean_return_pct=0.0,
                mean_range_pct=0.0,
                mean_volume_change_pct=0.0,
                persistence=round(float(transition[state, state]), 4),
            )
        else:
            summary = HMMStateSummary(
                state=state,
                regime=labels[state],
                sample_size=len(rows),
                mean_return_pct=round(float(rows[:, 0].mean()), 6),
                mean_range_pct=round(float(rows[:, 1].mean()), 6),
                mean_volume_change_pct=round(float(rows[:, 2].mean()), 6),
                persistence=round(float(transition[state, state]), 4),
            )
        summaries.append(summary)
    return sorted(summaries, key=lambda item: (item.sample_size, -item.state), reverse=True)


def describe_regime_switches(observations: list[HMMRegimeObservation]) -> int:
    regimes = [observation.hmm_regime for observation in observations]
    return sum(1 for previous, current in zip(regimes, regimes[1:], strict=False) if previous != current)


def sequence_stability(regimes: list[str]) -> float:
    if len(regimes) < 2:
        return 1.0
    switches = sum(1 for previous, current in zip(regimes, regimes[1:], strict=False) if previous != current)
    return round(1 - switches / (len(regimes) - 1), 4)
