from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RubberSourcePoint:
    key: str
    value: float
    unit: str
    source: str
    observed_at: datetime
    confidence: float
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "observed_at": self.observed_at.isoformat(),
            "confidence": self.confidence,
            "note": self.note,
        }


def rubber_seasonal_factor(month: int) -> float:
    if month in {12, 1, 2}:
        return 0.06
    if month in {3, 4}:
        return 0.04
    if month in {5, 6}:
        return 0.02
    if month in {7, 8, 9}:
        return -0.01
    return 0.0


def public_rubber_source_points(
    *,
    observed_at: datetime | None = None,
) -> list[RubberSourcePoint]:
    effective_at = observed_at or datetime.now(timezone.utc)
    return [
        RubberSourcePoint(
            key="thai_field_latex_cny",
            value=11200,
            unit="CNY/t",
            source="public_thailand_export_reference",
            observed_at=effective_at,
            confidence=0.62,
            note="Thailand origin latex/cup-lump public fallback estimate.",
        ),
        RubberSourcePoint(
            key="qingdao_bonded_spot_premium",
            value=320,
            unit="CNY/t",
            source="public_qingdao_bonded_zone",
            observed_at=effective_at,
            confidence=0.58,
            note="Qingdao bonded-zone spot premium public fallback.",
        ),
        RubberSourcePoint(
            key="hainan_yunnan_collection_cost",
            value=420,
            unit="CNY/t",
            source="public_domestic_origin_reference",
            observed_at=effective_at,
            confidence=0.55,
            note="Hainan/Yunnan collection and domestic logistics fallback.",
        ),
        RubberSourcePoint(
            key="ocean_freight",
            value=260,
            unit="CNY/t",
            source="public_freight_index_proxy",
            observed_at=effective_at,
            confidence=0.52,
            note="Drewry/CCFI-style public freight proxy for SEA to China.",
        ),
        RubberSourcePoint(
            key="import_tax_vat_fee",
            value=520,
            unit="CNY/t",
            source="manual_tax_parameter",
            observed_at=effective_at,
            confidence=0.65,
            note="Low-frequency import duty/VAT parameter; review quarterly.",
        ),
    ]


def public_rubber_inputs(*, observed_at: datetime | None = None) -> dict[str, float]:
    return {point.key: point.value for point in public_rubber_source_points(observed_at=observed_at)}
