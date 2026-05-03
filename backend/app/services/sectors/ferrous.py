from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BlastFurnaceMargin:
    rebar_price: float
    iron_ore_price: float
    coke_price: float
    conversion_fee: float
    margin: float
    margin_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "rebar_price": self.rebar_price,
            "iron_ore_price": self.iron_ore_price,
            "coke_price": self.coke_price,
            "conversion_fee": self.conversion_fee,
            "margin": round(self.margin, 4),
            "margin_pct": round(self.margin_pct, 6),
        }


def calculate_blast_furnace_margin(
    *,
    rebar_price: float,
    iron_ore_price: float,
    coke_price: float,
    conversion_fee: float = 760,
) -> BlastFurnaceMargin:
    raw_cost = 1.6 * iron_ore_price + 0.5 * coke_price + conversion_fee
    margin = rebar_price - raw_cost
    margin_pct = margin / rebar_price if rebar_price > 0 else 0.0
    return BlastFurnaceMargin(
        rebar_price=rebar_price,
        iron_ore_price=iron_ore_price,
        coke_price=coke_price,
        conversion_fee=conversion_fee,
        margin=margin,
        margin_pct=margin_pct,
    )
