from typing import Any

from app.services.cost_models.framework import CostFormula, CostModelResult, component, numeric_input


class CokingCoalCostFormula(CostFormula):
    symbol = "JM"
    name = "Coking Coal"
    capacity_cost_offsets = ((-0.12, 0.30), (-0.05, 0.30), (0.05, 0.25), (0.14, 0.15))

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        mining = numeric_input(inputs, "mining_cost", 930)
        washing = numeric_input(inputs, "washing_cost", 95)
        rail_freight = numeric_input(inputs, "rail_freight", 75)
        tax_fee = numeric_input(inputs, "tax_fee", 70)
        components = [
            component("mining_cost", mining.value),
            component("washing_cost", washing.value),
            component("rail_freight", rail_freight.value),
            component("tax_fee", tax_fee.value),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "mining_cost": mining,
                "washing_cost": washing,
                "rail_freight": rail_freight,
                "tax_fee": tax_fee,
            },
            current_price=current_price,
        )
