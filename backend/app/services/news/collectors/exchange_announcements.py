from app.services.news.types import NewsCollectorUnavailable, RawNewsItem


class ExchangeAnnouncementsCollector:
    source = "exchange_announcements"

    async def collect(self, limit: int = 50) -> list[RawNewsItem]:
        raise NewsCollectorUnavailable(
            "Exchange announcements collector is not connected to exchange feeds yet."
        )
