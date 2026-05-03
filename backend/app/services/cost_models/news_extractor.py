import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CostDataPoint:
    symbol: str
    component: str
    value: float
    unit: str
    source: str
    confidence: float
    observed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "component": self.component,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "confidence": self.confidence,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
        }


_SYMBOL_KEYWORDS = {
    "JM": ("coking coal", "met coal", "jiaomei", "焦煤"),
    "J": ("coke", "jiaotan", "焦炭"),
    "I": ("iron ore", "i230", "铁矿"),
    "RB": ("rebar", "螺纹"),
    "HC": ("hot coil", "热卷"),
    "NR": ("natural rubber", "latex", "cup lump", "天然橡胶", "20号胶", "胶水"),
    "RU": ("rubber", "shfe rubber", "天然橡胶", "沪胶", "橡胶"),
}

_COMPONENT_KEYWORDS = {
    "freight": ("freight", "shipping", "运费"),
    "ocean_freight": ("drewry", "ccfi", "ocean freight", "import freight", "海运费", "进口运费"),
    "processing_fee": ("processing", "conversion", "加工费"),
    "spot_price": ("spot", "现货", "均价"),
    "thai_field_latex_cny": ("thailand", "thai", "latex", "cup lump", "泰国", "胶水"),
    "qingdao_bonded_spot_premium": ("qingdao", "bonded", "保税区", "青岛"),
    "hainan_yunnan_collection_cost": ("hainan", "yunnan", "collection", "海南", "云南", "收胶"),
    "tax_fee": ("tax", "tariff", "关税"),
}


def extract_cost_data_points(
    *,
    title: str,
    content: str,
    source: str,
    published_at: datetime | None = None,
) -> list[CostDataPoint]:
    text = f"{title}\n{content}".lower()
    values = [float(match.group(1)) for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(?:yuan|cny|rmb|元)", text)]
    if not values:
        return []

    symbols = [symbol for symbol, keywords in _SYMBOL_KEYWORDS.items() if any(key.lower() in text for key in keywords)]
    components = [
        component
        for component, keywords in _COMPONENT_KEYWORDS.items()
        if any(key.lower() in text for key in keywords)
    ]
    if not symbols:
        symbols = ["UNKNOWN"]
    if not components:
        components = ["spot_price"]

    confidence = 0.75 if len(symbols) == 1 and len(components) == 1 else 0.55
    return [
        CostDataPoint(
            symbol=symbol,
            component=component,
            value=value,
            unit="CNY/t",
            source=source,
            confidence=confidence,
            observed_at=published_at,
        )
        for symbol in symbols
        for component in components
        for value in values[:3]
    ]
