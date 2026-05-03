from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.news.types import RawNewsItem

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltCollector:
    source = "gdelt"

    def __init__(self, query: str = "commodities futures", timeout: float = 15.0) -> None:
        self.query = query
        self.timeout = timeout

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        params = {
            "query": self.query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(limit, 250),
            "sort": "hybridrel",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(GDELT_DOC_API, params=params)
            response.raise_for_status()
            data = response.json()
        return [self._item_from_article(article) for article in data.get("articles", [])]

    def _item_from_article(self, article: dict[str, Any]) -> RawNewsItem:
        published_at = _parse_gdelt_datetime(article.get("seendate"))
        return RawNewsItem(
            source=self.source,
            title=str(article.get("title") or "Untitled GDELT article"),
            raw_url=article.get("url"),
            content_text=article.get("sourcecountry"),
            published_at=published_at,
            metadata={
                "domain": article.get("domain"),
                "language": article.get("language"),
                "source_country": article.get("sourcecountry"),
            },
        )


def _parse_gdelt_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.strptime(value[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)
