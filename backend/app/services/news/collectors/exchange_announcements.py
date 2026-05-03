from app.services.news.types import RawNewsItem


class ExchangeAnnouncementsCollector:
    source = "exchange_announcements"

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        return []
