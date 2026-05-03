from typing import Any

from app.services.cost_models.framework import CostFormula, CostModelResult, component, numeric_input


class RebarCostFormula(CostFormula):
    symbol = "RB"
    name = "Rebar"
    capacity_cost_offsets = ((-0.08, 0.20), (-0.03, 0.30), (0.05, 0.30), (0.13, 0.20))

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        iron_ore_cost = upstream.get("I").unit_cost if upstream and upstream.get("I") else 880
        coke_cost = upstream.get("J").unit_cost if upstream and upstream.get("J") else 1920
        iron_ratio = numeric_input(inputs, "iron_ore_ratio", 1.60, unit="t/t")
        coke_ratio = numeric_input(inputs, "coke_ratio", 0.50, unit="t/t")
        conversion = numeric_input(inputs, "blast_furnace_conversion_fee", 760)
        scrap_credit = numeric_input(inputs, "scrap_credit", 90)
        freight_tax = numeric_input(inputs, "freight_tax_fee", 160)

        ore_component = iron_ore_cost * iron_ratio.value
        coke_component = coke_cost * coke_ratio.value
        components = [
            component("iron_ore_charge", ore_component),
            component("coke_charge", coke_component),
            component("blast_furnace_conversion_fee", conversion.value),
            component("freight_tax_fee", freight_tax.value),
            component("scrap_credit", -scrap_credit.value),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "upstream_i_unit_cost": numeric_input(
                    {"upstream_i_unit_cost": iron_ore_cost},
                    "upstream_i_unit_cost",
                    iron_ore_cost,
                ),
                "upstream_j_unit_cost": numeric_input(
                    {"upstream_j_unit_cost": coke_cost},
                    "upstream_j_unit_cost",
                    coke_cost,
                ),
                "iron_ore_ratio": iron_ratio,
                "coke_ratio": coke_ratio,
                "blast_furnace_conversion_fee": conversion,
                "scrap_credit": scrap_credit,
                "freight_tax_fee": freight_tax,
            },
            current_price=current_price,
        )
