from app.services.cost_models.configs.coke import CokeCostFormula
from app.services.cost_models.configs.coking_coal import CokingCoalCostFormula
from app.services.cost_models.configs.hot_coil import HotCoilCostFormula
from app.services.cost_models.configs.iron_ore import IronOreCostFormula
from app.services.cost_models.configs.rebar import RebarCostFormula

FERROUS_FORMULAS = {
    "JM": CokingCoalCostFormula(),
    "J": CokeCostFormula(),
    "I": IronOreCostFormula(),
    "RB": RebarCostFormula(),
    "HC": HotCoilCostFormula(),
}

__all__ = [
    "CokeCostFormula",
    "CokingCoalCostFormula",
    "FERROUS_FORMULAS",
    "HotCoilCostFormula",
    "IronOreCostFormula",
    "RebarCostFormula",
]
