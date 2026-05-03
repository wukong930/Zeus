from typing import Any

from app.services.cost_models.framework import CostFormula, CostModelResult, component, numeric_input


class IronOreCostFormula(CostFormula):
    symbol = "I"
    name = "Iron Ore"
    capacity_cost_offsets = ((-0.18, 0.35), (-0.06, 0.30), (0.08, 0.20), (0.20, 0.15))

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        index_price = numeric_input(inputs, "iron_ore_index_cny", 760)
        ocean_freight = numeric_input(inputs, "ocean_freight", 55)
        port_fee = numeric_input(inputs, "port_fee", 25)
        finance_cost = numeric_input(inputs, "finance_cost", 18)
        tax_fee = numeric_input(inputs, "tax_fee", 22)
        components = [
            component("iron_ore_index_cny", index_price.value),
            component("ocean_freight", ocean_freight.value),
            component("port_fee", port_fee.value),
            component("finance_cost", finance_cost.value),
            component("tax_fee", tax_fee.value),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "iron_ore_index_cny": index_price,
                "ocean_freight": ocean_freight,
                "port_fee": port_fee,
                "finance_cost": finance_cost,
                "tax_fee": tax_fee,
            },
            current_price=current_price,
        )
