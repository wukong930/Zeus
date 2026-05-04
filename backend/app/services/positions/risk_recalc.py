from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.position import Position
from app.services.risk.correlation import build_correlation_matrix
from app.services.risk.market_data import load_risk_market_data
from app.services.risk.types import RiskLeg, RiskPosition
from app.services.risk.var import calculate_var

CONCENTRATION_LIMIT = 0.55


@dataclass(frozen=True)
class PositionRiskSnapshot:
    open_positions: int
    total_margin_used: float
    largest_symbol: str | None
    largest_symbol_margin: float
    concentration_ratio: float
    var95: float
    var99: float
    correlation_symbols: list[str]
    degraded_new_recommendations: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "open_positions": self.open_positions,
            "total_margin_used": self.total_margin_used,
            "largest_symbol": self.largest_symbol,
            "largest_symbol_margin": self.largest_symbol_margin,
            "concentration_ratio": self.concentration_ratio,
            "var95": self.var95,
            "var99": self.var99,
            "correlation_symbols": self.correlation_symbols,
            "degraded_new_recommendations": self.degraded_new_recommendations,
            "warnings": self.warnings,
        }


async def recalculate_position_risk(session: AsyncSession) -> PositionRiskSnapshot:
    rows = (
        await session.scalars(
            select(Position).where(Position.status == "open").order_by(Position.opened_at.desc())
        )
    ).all()
    margin_by_symbol: dict[str, float] = {}
    total_margin = 0.0
    for row in rows:
        margin = float(row.total_margin_used or 0)
        total_margin += margin
        symbols = position_symbols(row)
        if not symbols:
            continue
        split_margin = margin / len(symbols)
        for symbol in symbols:
            margin_by_symbol[symbol] = margin_by_symbol.get(symbol, 0.0) + split_margin

    largest_symbol = None
    largest_margin = 0.0
    if margin_by_symbol:
        largest_symbol, largest_margin = max(margin_by_symbol.items(), key=lambda item: item[1])
    concentration = largest_margin / total_margin if total_margin > 0 else 0.0
    warnings: list[str] = []
    if concentration >= CONCENTRATION_LIMIT:
        warnings.append(f"{largest_symbol} concentration {concentration:.0%} exceeds limit")

    risk_positions = [_position_to_risk_position(row) for row in rows]
    symbols = sorted({leg.asset for position in risk_positions for leg in position.legs if leg.asset})
    market_data = await load_risk_market_data(session, symbols, limit=252)
    var_result = calculate_var(risk_positions, market_data)
    correlation = build_correlation_matrix(market_data, symbols, window=60)

    return PositionRiskSnapshot(
        open_positions=len(rows),
        total_margin_used=round(total_margin, 2),
        largest_symbol=largest_symbol,
        largest_symbol_margin=round(largest_margin, 2),
        concentration_ratio=round(concentration, 4),
        var95=var_result.var95,
        var99=var_result.var99,
        correlation_symbols=list(correlation.symbols),
        degraded_new_recommendations=bool(warnings),
        warnings=warnings,
    )


def position_symbols(position: Position) -> set[str]:
    symbols: set[str] = set()
    for leg in position.legs or []:
        if isinstance(leg, dict):
            value = str(leg.get("asset") or leg.get("symbol") or "").strip().upper()
            if value:
                symbols.add(value)
    return symbols


def _position_to_risk_position(position: Position) -> RiskPosition:
    return RiskPosition(
        id=str(position.id),
        strategy_name=position.strategy_name,
        status=position.status,
        legs=tuple(_leg_from_payload(leg) for leg in position.legs if isinstance(leg, dict)),
    )


def _leg_from_payload(payload: dict) -> RiskLeg:
    asset = str(payload.get("asset") or payload.get("symbol") or "")
    direction = "short" if str(payload.get("direction", "long")).lower() == "short" else "long"
    return RiskLeg(
        asset=asset,
        direction=direction,
        size=float(payload.get("size") or payload.get("quantity") or payload.get("lots") or 0),
        current_price=float(
            payload.get("currentPrice")
            or payload.get("current_price")
            or payload.get("price")
            or payload.get("entry_price")
            or 0
        ),
        entry_price=(
            float(payload["entry_price"])
            if payload.get("entry_price") is not None
            else None
        ),
        unit=payload.get("unit"),
        unrealized_pnl=(
            float(payload["unrealized_pnl"])
            if payload.get("unrealized_pnl") is not None
            else None
        ),
        margin_used=(
            float(payload["margin_used"])
            if payload.get("margin_used") is not None
            else None
        ),
    )
