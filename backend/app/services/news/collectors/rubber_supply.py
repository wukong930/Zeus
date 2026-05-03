from app.services.news.collectors.gdelt import GdeltCollector
from app.services.news.types import RawNewsItem

RUBBER_SUPPLY_GDELT_QUERY = (
    '(rubber OR latex OR "natural rubber" OR "rubber tapping") '
    '(Thailand OR Indonesia OR Malaysia OR Vietnam OR Hainan OR Yunnan OR Qingdao '
    'OR flood OR rainfall OR drought OR export OR policy)'
)


class RubberSupplyCollector:
    source = "rubber_supply_gdelt"

    def __init__(self, gdelt: GdeltCollector | None = None) -> None:
        self.gdelt = gdelt or GdeltCollector(query=RUBBER_SUPPLY_GDELT_QUERY)

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        items = await self.gdelt.collect(limit=limit)
        return [self._enrich(item) for item in items if is_rubber_supply_relevant(item)]

    def _enrich(self, item: RawNewsItem) -> RawNewsItem:
        metadata = {
            **item.metadata,
            "upstream_source": item.source,
            "collector_family": "rubber_supply",
            "affected_symbols": ["NR", "RU"],
            "source_count": int(item.metadata.get("source_count") or 1),
            "origin_markets": origin_markets(item),
        }
        return RawNewsItem(
            source=self.source,
            title=item.title,
            published_at=item.published_at,
            raw_url=item.raw_url,
            content_text=item.content_text,
            metadata=metadata,
        )


def is_rubber_supply_relevant(item: RawNewsItem) -> bool:
    text = f"{item.title} {item.content_text or ''}".lower()
    rubber_hit = any(
        marker in text
        for marker in (
            "rubber",
            "latex",
            "cup lump",
            "natural rubber",
            "rubber tapping",
            "天然橡胶",
            "橡胶",
            "胶水",
            "割胶",
        )
    )
    supply_hit = any(
        marker in text
        for marker in (
            "thailand",
            "indonesia",
            "malaysia",
            "vietnam",
            "hainan",
            "yunnan",
            "qingdao",
            "flood",
            "rain",
            "rainfall",
            "storm",
            "drought",
            "monsoon",
            "export",
            "tariff",
            "policy",
            "供应",
            "出口",
            "天气",
            "暴雨",
            "干旱",
            "洪水",
        )
    )
    return rubber_hit and supply_hit


def origin_markets(item: RawNewsItem) -> list[str]:
    text = f"{item.title} {item.content_text or ''}".lower()
    origins = []
    for label, markers in {
        "Thailand": ("thailand", "thai", "泰国"),
        "Indonesia": ("indonesia", "印尼", "印度尼西亚"),
        "Malaysia": ("malaysia", "马来西亚"),
        "Vietnam": ("vietnam", "越南"),
        "Hainan": ("hainan", "海南"),
        "Yunnan": ("yunnan", "云南"),
        "Qingdao": ("qingdao", "青岛"),
    }.items():
        if any(marker in text for marker in markers):
            origins.append(label)
    return origins
