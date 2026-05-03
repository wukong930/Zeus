from typing import Any

from app.services.cost_models.framework import CostFormula, CostModelResult, component, numeric_input


class CokeCostFormula(CostFormula):
    symbol = "J"
    name = "Coke"
    capacity_cost_offsets = ((-0.10, 0.25), (-0.03, 0.30), (0.06, 0.25), (0.15, 0.20))

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        upstream_cost = upstream.get("JM").unit_cost if upstream and upstream.get("JM") else 1170
        coal_ratio = numeric_input(inputs, "coal_ratio", 1.34, unit="t/t")
        processing = numeric_input(inputs, "coking_processing_fee", 250)
        energy = numeric_input(inputs, "energy_and_labor", 85)
        freight = numeric_input(inputs, "freight_and_storage", 70)
        tax_fee = numeric_input(inputs, "tax_fee", 65)
        byproduct_credit = numeric_input(inputs, "byproduct_credit", 120)

        raw_coal = upstream_cost * coal_ratio.value
        components = [
            component("raw_coking_coal", raw_coal),
            component("coking_processing_fee", processing.value),
            component("energy_and_labor", energy.value),
            component("freight_and_storage", freight.value),
            component("tax_fee", tax_fee.value),
            component("byproduct_credit", -byproduct_credit.value),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "upstream_jm_unit_cost": numeric_input(
                    {"upstream_jm_unit_cost": upstream_cost},
                    "upstream_jm_unit_cost",
                    upstream_cost,
                ),
                "coal_ratio": coal_ratio,
                "coking_processing_fee": processing,
                "energy_and_labor": energy,
                "freight_and_storage": freight,
                "tax_fee": tax_fee,
                "byproduct_credit": byproduct_credit,
            },
            current_price=current_price,
        )
