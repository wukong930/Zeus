from typing import Any

from app.services.cost_models.framework import CostFormula, CostInput, CostModelResult, component, numeric_input


class RubberProcessedCostFormula(CostFormula):
    symbol = "RU"
    name = "SHFE Rubber"
    sector = "rubber"
    version = "phase7b.v1"
    capacity_cost_offsets = ((-0.10, 0.20), (-0.03, 0.30), (0.05, 0.30), (0.14, 0.20))
    uncertainty_pct = 0.07

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        nr_cost = upstream.get("NR").unit_cost if upstream and upstream.get("NR") else 13000
        raw_ratio = numeric_input(inputs, "raw_rubber_ratio", 1.03, unit="t/t")
        processing = numeric_input(inputs, "ru_processing_fee", 950)
        grade_premium = numeric_input(inputs, "grade_premium", 260)
        warehouse = numeric_input(inputs, "warehouse_finance_fee", 180)
        exchange_delivery = numeric_input(inputs, "exchange_delivery_fee", 120)
        loss_fee = numeric_input(inputs, "loss_adjustment_fee", 160)

        raw_material = nr_cost * raw_ratio.value
        components = [
            component("upstream_nr_charge", raw_material),
            component("ru_processing_fee", processing.value),
            component("grade_premium", grade_premium.value),
            component("warehouse_finance_fee", warehouse.value),
            component("exchange_delivery_fee", exchange_delivery.value),
            component("loss_adjustment_fee", loss_fee.value),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "upstream_nr_unit_cost": CostInput(
                    name="upstream_nr_unit_cost",
                    value=nr_cost,
                    unit="CNY/t",
                    source="public_fallback",
                    uncertainty_pct=self.uncertainty_pct,
                ),
                "raw_rubber_ratio": raw_ratio,
                "ru_processing_fee": processing,
                "grade_premium": grade_premium,
                "warehouse_finance_fee": warehouse,
                "exchange_delivery_fee": exchange_delivery,
                "loss_adjustment_fee": loss_fee,
            },
            current_price=current_price,
        )
