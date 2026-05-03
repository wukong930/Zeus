from datetime import datetime, timezone
from typing import Any

from app.services.cost_models.framework import CostFormula, CostModelResult, component, numeric_input
from app.services.cost_models.rubber_sources import public_rubber_inputs, rubber_seasonal_factor


class NaturalRubberCostFormula(CostFormula):
    symbol = "NR"
    name = "Natural Rubber"
    sector = "rubber"
    version = "phase7b.v1"
    capacity_cost_offsets = ((-0.12, 0.20), (-0.04, 0.30), (0.06, 0.30), (0.18, 0.20))
    uncertainty_pct = 0.07

    def calculate(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        upstream: dict[str, CostModelResult] | None = None,
        current_price: float | None = None,
    ) -> CostModelResult:
        del upstream
        defaults = public_rubber_inputs()
        observed_month = int((inputs or {}).get("seasonal_month") or datetime.now(timezone.utc).month)
        seasonal_factor = numeric_input(
            inputs,
            "seasonal_factor_pct",
            rubber_seasonal_factor(observed_month),
            unit="pct",
        )
        origin = numeric_input(inputs, "thai_field_latex_cny", defaults["thai_field_latex_cny"])
        qingdao_premium = numeric_input(
            inputs,
            "qingdao_bonded_spot_premium",
            defaults["qingdao_bonded_spot_premium"],
        )
        domestic_collection = numeric_input(
            inputs,
            "hainan_yunnan_collection_cost",
            defaults["hainan_yunnan_collection_cost"],
        )
        processing = numeric_input(inputs, "primary_processing_fee", 280)
        freight = numeric_input(inputs, "ocean_freight", defaults["ocean_freight"])
        tax_fee = numeric_input(inputs, "import_tax_vat_fee", defaults["import_tax_vat_fee"])

        base_cost = (
            origin.value
            + qingdao_premium.value
            + domestic_collection.value
            + processing.value
            + freight.value
            + tax_fee.value
        )
        seasonal_premium = base_cost * seasonal_factor.value
        components = [
            component("thai_field_latex_cny", origin.value),
            component("qingdao_bonded_spot_premium", qingdao_premium.value),
            component("hainan_yunnan_collection_cost", domestic_collection.value),
            component("primary_processing_fee", processing.value),
            component("ocean_freight", freight.value),
            component("import_tax_vat_fee", tax_fee.value),
            component("seasonal_premium", seasonal_premium),
        ]
        return self.result(
            unit_cost=sum(item.value for item in components),
            components=components,
            inputs={
                "thai_field_latex_cny": origin,
                "qingdao_bonded_spot_premium": qingdao_premium,
                "hainan_yunnan_collection_cost": domestic_collection,
                "primary_processing_fee": processing,
                "ocean_freight": freight,
                "import_tax_vat_fee": tax_fee,
                "seasonal_factor_pct": seasonal_factor,
            },
            current_price=current_price,
        )
