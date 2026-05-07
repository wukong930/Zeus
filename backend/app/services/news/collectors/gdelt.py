from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.news.types import RawNewsItem

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltCollector:
    source = "gdelt"

    def __init__(
        self,
        query: str = "commodities futures",
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.query = query
        self.timeout = timeout
        self.transport = transport

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        params = {
            "query": self.query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(limit, 250),
            "sort": "hybridrel",
        }
        headers = {
            "Accept": "application/json",
            "User-Agent": "Zeus/0.1 data-source-ingest",
        }
        async with httpx.AsyncClient(
            timeout=self.timeout,
            transport=self.transport,
            headers=headers,
        ) as client:
            response = await client.get(GDELT_DOC_API, params=params)
            if response.status_code == 204:
                return []
            if response.status_code == 429:
                raise RuntimeError("GDELT rate limited the DOC API request")
            response.raise_for_status()
            if not response.content.strip():
                return []
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("GDELT returned invalid JSON") from exc
        articles = _articles_from_payload(data)
        return [self._item_from_article(article) for article in articles]

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


def _articles_from_payload(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise RuntimeError("GDELT payload must be a JSON object")
    articles = payload.get("articles", [])
    if not isinstance(articles, list):
        raise RuntimeError("GDELT payload articles must be a list")
    if any(not isinstance(article, dict) for article in articles):
        raise RuntimeError("GDELT payload articles must contain objects")
    return articles
