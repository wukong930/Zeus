from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

from app.services.calibration.tracker import (
    DEFAULT_CALIBRATION_WEIGHT,
    get_calibration_weight,
)


class _FakeScalarResult:
    def first(self):
        return None


class _CapturingSession:
    def __init__(self):
        self.statements = []

    async def scalars(self, statement):
        self.statements.append(statement)
        return _FakeScalarResult()


async def test_get_calibration_weight_binds_the_provided_as_of_not_wall_clock():
    # The decision-path contract: as_of is required and is used verbatim, so a
    # caller can never silently read the latest (future-leaking) calibration.
    session = _CapturingSession()
    as_of = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    weight = await get_calibration_weight(
        session,  # type: ignore[arg-type]
        signal_type="momentum",
        category="ferrous",
        regime="trend",
        as_of=as_of,
    )

    assert weight == DEFAULT_CALIBRATION_WEIGHT  # no rows -> default
    assert session.statements
    sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "2024-01-02 03:04:05" in sql


async def test_get_calibration_weight_without_session_returns_default():
    weight = await get_calibration_weight(
        None,
        signal_type="momentum",
        category="ferrous",
        regime="trend",
        as_of=datetime(2024, 1, 2, tzinfo=timezone.utc),
    )
    assert weight == DEFAULT_CALIBRATION_WEIGHT
