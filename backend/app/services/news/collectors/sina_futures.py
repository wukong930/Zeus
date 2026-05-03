from app.services.news.types import RawNewsItem


class SinaFuturesCollector:
    source = "sina_futures"

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        return []
