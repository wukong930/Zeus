from app.services.cost_models.configs.coke import CokeCostFormula
from app.services.cost_models.configs.coking_coal import CokingCoalCostFormula
from app.services.cost_models.configs.hot_coil import HotCoilCostFormula
from app.services.cost_models.configs.iron_ore import IronOreCostFormula
from app.services.cost_models.configs.natural_rubber import NaturalRubberCostFormula
from app.services.cost_models.configs.rebar import RebarCostFormula
from app.services.cost_models.configs.rubber_processed import RubberProcessedCostFormula

FERROUS_FORMULAS = {
    "JM": CokingCoalCostFormula(),
    "J": CokeCostFormula(),
    "I": IronOreCostFormula(),
    "RB": RebarCostFormula(),
    "HC": HotCoilCostFormula(),
}
RUBBER_FORMULAS = {
    "NR": NaturalRubberCostFormula(),
    "RU": RubberProcessedCostFormula(),
}
ALL_COST_FORMULAS = {
    **FERROUS_FORMULAS,
    **RUBBER_FORMULAS,
}

__all__ = [
    "ALL_COST_FORMULAS",
    "CokeCostFormula",
    "CokingCoalCostFormula",
    "FERROUS_FORMULAS",
    "HotCoilCostFormula",
    "IronOreCostFormula",
    "NaturalRubberCostFormula",
    "RebarCostFormula",
    "RUBBER_FORMULAS",
    "RubberProcessedCostFormula",
]
