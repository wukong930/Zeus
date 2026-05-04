from dataclasses import dataclass
from typing import Any


class DataSourceUnavailable(RuntimeError):
    """Raised when a configured source cannot run in the current environment."""


@dataclass(frozen=True)
class DataSourceStatus:
    id: str
    name: str
    category: str
    enabled: bool
    configured: bool
    requires_key: bool
    free_tier: str
    status: str
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "enabled": self.enabled,
            "configured": self.configured,
            "requires_key": self.requires_key,
            "free_tier": self.free_tier,
            "status": self.status,
            "note": self.note,
        }
