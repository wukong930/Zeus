from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EventIntelligenceEvalCase:
    id: str
    title: str
    source_text: str
    expected_symbols: tuple[str, ...]
    expected_mechanisms: tuple[str, ...]
    expected_directions: tuple[str, ...]
    review_note: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["expected_symbols"] = list(self.expected_symbols)
        payload["expected_mechanisms"] = list(self.expected_mechanisms)
        payload["expected_directions"] = list(self.expected_directions)
        return payload


EVENT_INTELLIGENCE_EVAL_CASES: tuple[EventIntelligenceEvalCase, ...] = (
    EventIntelligenceEvalCase(
        id="rubber-weather-el-nino",
        title="Rubber rainfall anomaly and El Nino probability",
        source_text=(
            "Southeast Asia rubber tapping regions report below-normal rainfall while El Nino "
            "probability rises, increasing risk of reduced latex output."
        ),
        expected_symbols=("RU", "NR", "BR"),
        expected_mechanisms=("weather", "supply"),
        expected_directions=("bullish", "watch"),
        review_note="Weather can tighten RU/NR supply directly; BR is secondary through substitution.",
    ),
    EventIntelligenceEvalCase(
        id="carrier-iran-crude",
        title="US carrier group moves toward the Strait of Hormuz",
        source_text=(
            "A carrier group is reportedly moving toward the Iran/Hormuz area. Shipping risk "
            "may raise crude risk premium, but demand impact remains uncertain."
        ),
        expected_symbols=("SC",),
        expected_mechanisms=("geopolitical", "logistics", "risk_sentiment"),
        expected_directions=("bullish", "watch"),
        review_note="Single-source military claims need manual review before confirming direction.",
    ),
    EventIntelligenceEvalCase(
        id="tariff-ferrous-base-metals",
        title="Trump tariff post hits industrial metals sentiment",
        source_text=(
            "A new tariff threat from Trump triggers risk-off selling in industrial metals and "
            "steel-related contracts as trade policy uncertainty rises."
        ),
        expected_symbols=("CU", "AL", "RB", "HC", "I"),
        expected_mechanisms=("policy", "macro", "risk_sentiment", "demand"),
        expected_directions=("bearish", "mixed"),
        review_note="Policy shock can pressure demand sentiment while also raising cost-chain risk.",
    ),
    EventIntelligenceEvalCase(
        id="port-flood-logistics",
        title="Flooding disrupts port and inland freight",
        source_text=(
            "Flooding near a major port slows vessel loading and inland freight. Ore, rubber and "
            "agricultural cargoes face delivery delays."
        ),
        expected_symbols=("I", "RU", "NR", "M", "Y", "P"),
        expected_mechanisms=("weather", "logistics", "supply"),
        expected_directions=("bullish", "watch"),
        review_note="Same factor can affect several commodities through transport rather than output.",
    ),
    EventIntelligenceEvalCase(
        id="soy-biofuel-policy",
        title="Biofuel policy lifts soybean oil demand expectations",
        source_text=(
            "Biofuel blending policy expansion improves soybean oil demand expectations while "
            "soymeal impact is indirect through crush margins."
        ),
        expected_symbols=("Y", "M"),
        expected_mechanisms=("policy", "demand", "supply"),
        expected_directions=("bullish", "mixed"),
        review_note="The engine should distinguish direct Y demand from indirect M/crush effects.",
    ),
)
