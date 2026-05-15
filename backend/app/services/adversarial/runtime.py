from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_agent import AlertAgentConfig

ADVERSARIAL_RUNTIME_KEY = "adversarial_runtime"
DEFAULT_WARMUP_ENABLED = True


@dataclass(frozen=True)
class AdversarialRuntimeConfig:
    warmup_enabled: bool
    source: str

    @property
    def mode(self) -> str:
        return "warmup" if self.warmup_enabled else "enforcing"

    @property
    def historical_combo_mode(self) -> str:
        return "informational" if self.warmup_enabled else "sample_based_enforcing"

    @property
    def production_effect(self) -> str:
        return "observe_only" if self.warmup_enabled else "may_suppress_signals"


async def load_adversarial_runtime_config(
    session: AsyncSession | None,
) -> AdversarialRuntimeConfig:
    if session is None:
        return default_adversarial_runtime_config()

    row = await _adversarial_runtime_row(session)
    if row is None:
        return default_adversarial_runtime_config()
    return _runtime_config_from_values(row.value or {}, source="database")


async def save_adversarial_runtime_config(
    session: AsyncSession,
    *,
    warmup_enabled: bool,
) -> AdversarialRuntimeConfig:
    values = {"warmup_enabled": bool(warmup_enabled)}
    row = await _adversarial_runtime_row(session)
    if row is None:
        row = AlertAgentConfig(key=ADVERSARIAL_RUNTIME_KEY, value=values)
        session.add(row)
    else:
        row.value = values

    await session.commit()
    return _runtime_config_from_values(values, source="database")


def default_adversarial_runtime_config() -> AdversarialRuntimeConfig:
    return AdversarialRuntimeConfig(
        warmup_enabled=DEFAULT_WARMUP_ENABLED,
        source="backend_defaults",
    )


async def _adversarial_runtime_row(session: AsyncSession) -> AlertAgentConfig | None:
    return (
        await session.scalars(
            select(AlertAgentConfig)
            .where(AlertAgentConfig.key == ADVERSARIAL_RUNTIME_KEY)
            .limit(1)
        )
    ).first()


def _runtime_config_from_values(values: dict[str, Any], *, source: str) -> AdversarialRuntimeConfig:
    return AdversarialRuntimeConfig(
        warmup_enabled=_bool_value(values.get("warmup_enabled"), DEFAULT_WARMUP_ENABLED),
        source=source,
    )


def _bool_value(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default
