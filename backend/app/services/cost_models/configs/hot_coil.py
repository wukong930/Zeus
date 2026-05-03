from typing import Any

from app.services.cost_models.framework import CostFormula, CostModelResult, component, numeric_input


class HotCoilCostFormula(CostFormula):
    symbol = "HC"
    name = "Hot Coil"
    capacity_cost_offsets = ((-0.07, 0.20), (-0.02, 0.30), (0.05, 0.30), (0.12, 0.20))

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        base_rebar_cost = upstream.get("RB").unit_cost if upstream and upstream.get("RB") else 3740
        hot_rolling_delta = numeric_input(inputs, "hot_rolling_delta", 180)
        quality_premium = numeric_input(inputs, "quality_premium", 65)
        freight_tax = numeric_input(inputs, "freight_tax_fee", 45)
        components = [
            component("blast_furnace_base", base_rebar_cost),
            component("hot_rolling_delta", hot_rolling_delta.value),
            component("quality_premium", quality_premium.value),
            component("freight_tax_fee", freight_tax.value),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "upstream_rb_unit_cost": numeric_input(
                    {"upstream_rb_unit_cost": base_rebar_cost},
                    "upstream_rb_unit_cost",
                    base_rebar_cost,
                ),
                "hot_rolling_delta": hot_rolling_delta,
                "quality_premium": quality_premium,
                "freight_tax_fee": freight_tax,
            },
            current_price=current_price,
        )
