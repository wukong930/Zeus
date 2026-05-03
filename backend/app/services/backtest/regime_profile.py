from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.services.backtest.multiple_testing import sharpe_ratio
from app.services.backtest.path_metrics import calculate_path_metrics


@dataclass(frozen=True, slots=True)
class RegimeObservation:
    regime: str
    return_pct: float


@dataclass(frozen=True, slots=True)
class RegimeProfileSlice:
    regime: str
    sample_size: int
    win_rate: float
    sharpe: float
    max_drawdown: float
    cvar95: float

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "sample_size": self.sample_size,
            "win_rate": round(self.win_rate, 6),
            "sharpe": round(self.sharpe, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "cvar95": round(self.cvar95, 6),
        }


def build_regime_profile(
    observations: list[RegimeObservation],
    *,
    periods_per_year: int = 252,
) -> list[RegimeProfileSlice]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        grouped[observation.regime or "unknown"].append(observation.return_pct)

    slices: list[RegimeProfileSlice] = []
    for regime, returns in sorted(grouped.items()):
        path = calculate_path_metrics(returns)
        slices.append(
            RegimeProfileSlice(
                regime=regime,
                sample_size=len(returns),
                win_rate=sum(1 for item in returns if item > 0) / len(returns) if returns else 0.0,
                sharpe=sharpe_ratio(returns, periods_per_year=periods_per_year),
                max_drawdown=path.max_drawdown,
                cvar95=path.cvar95,
            )
        )
    return slices
