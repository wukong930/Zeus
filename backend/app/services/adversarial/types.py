from dataclasses import dataclass
from typing import Any

MODE_ENFORCING = "enforcing"
MODE_INFORMATIONAL = "informational"


@dataclass(frozen=True)
class AdversarialCheckResult:
    check_name: str
    passed: bool
    mode: str = MODE_ENFORCING
    score: float | None = None
    sample_size: int = 0
    reason: str | None = None
    details: dict[str, Any] | None = None

    @property
    def enforcing_failure(self) -> bool:
        return self.mode == MODE_ENFORCING and not self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "mode": self.mode,
            "score": self.score,
            "sample_size": self.sample_size,
            "reason": self.reason,
            "details": self.details or {},
        }
