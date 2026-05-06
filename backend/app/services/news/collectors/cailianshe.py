from app.services.news.types import NewsCollectorUnavailable, RawNewsItem


class CailiansheCollector:
    source = "cailianshe"

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        raise NewsCollectorUnavailable(
            "Cailianshe collector is not connected to an approved runtime feed."
        )
