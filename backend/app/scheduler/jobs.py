from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


JobHandler = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class JobDefinition:
    id: str
    name: str
    cron: str
    enabled: bool = True


DEFAULT_JOB_DEFINITIONS: tuple[JobDefinition, ...] = (
    JobDefinition("ingest", "行情数据", "5 10,11,14,15 * * 1-5"),
    JobDefinition("context", "上下文刷新", "0 */4 * * *"),
    JobDefinition("alerts", "预警触发", "0 * * * *"),
    JobDefinition("evolution", "假设演化", "0 8 * * *"),
    JobDefinition("risk", "风险计算", "30 8 * * *"),
    JobDefinition("auto-eval", "信号评判", "0 9 * * *"),
    JobDefinition("track-outcomes", "绩效追踪", "30 16 * * 1-5"),
    JobDefinition("cleanup", "数据清理", "0 3 * * *"),
    JobDefinition("main-contract", "主力合约日检", "10 16 * * 1-5"),
)


async def placeholder_job() -> dict[str, Any]:
    return {
        "status": "noop",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


DEFAULT_JOB_HANDLERS: dict[str, JobHandler] = {
    definition.id: placeholder_job for definition in DEFAULT_JOB_DEFINITIONS
}
