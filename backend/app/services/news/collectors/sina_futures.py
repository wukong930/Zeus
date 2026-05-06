from app.services.news.types import NewsCollectorUnavailable, RawNewsItem


class SinaFuturesCollector:
    source = "sina_futures"

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        raise NewsCollectorUnavailable(
            "Sina futures collector is not connected to an approved runtime feed."
        )
