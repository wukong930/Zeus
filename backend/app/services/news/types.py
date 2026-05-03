from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class RawNewsItem:
    source: str
    title: str
    published_at: datetime
    raw_url: str | None = None
    content_text: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.published_at.tzinfo is None:
            object.__setattr__(self, "published_at", self.published_at.replace(tzinfo=timezone.utc))
