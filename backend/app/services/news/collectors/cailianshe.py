from app.services.news.types import RawNewsItem


class CailiansheCollector:
    source = "cailianshe"

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        return []
