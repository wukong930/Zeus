from sqlalchemy.dialects import postgresql

from app.services.adversarial.engine import load_historical_combo_candidates
from app.services.adversarial.historical_combo import (
    HistoricalComboCandidate,
    best_historical_candidate,
)


def _candidate(types, sample, *, hit=0.5, category="ferrous", regime="trend"):
    return HistoricalComboCandidate(
        signal_types=frozenset(types),
        category=category,
        regime=regime,
        hit_rate=hit,
        sample_size=sample,
    )


def test_best_candidate_is_deterministic_under_input_reordering():
    # Two candidates tied on BOTH similarity (0.5 each vs the query) and
    # sample_size. Before the fix the winner depended on row order, which is
    # non-deterministic and would leak into enforcing-mode decisions.
    a = _candidate({"momentum"}, 30)
    b = _candidate({"basis_shift"}, 30)
    kwargs = dict(
        signal_types={"momentum", "basis_shift"},
        category="ferrous",
        regime="trend",
        min_similarity=0.0,
    )

    first, first_sim = best_historical_candidate(candidates=[a, b], **kwargs)
    second, second_sim = best_historical_candidate(candidates=[b, a], **kwargs)

    assert first is not None and second is not None
    assert first_sim == second_sim == 0.5
    assert first.signal_types == second.signal_types
    # tiebreaker is the lexicographically smallest signal_types tuple
    assert first.signal_types == frozenset({"basis_shift"})


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.captured = None

    async def scalars(self, statement):
        self.captured = statement
        return _FakeScalars(self._rows)


async def test_candidate_query_has_deterministic_order_by():
    session = _FakeSession([])

    await load_historical_combo_candidates(session, category="ferrous", regime="trend")

    sql = str(session.captured.compile(dialect=postgresql.dialect())).lower()
    assert "order by signal_calibration.signal_type asc" in sql
    assert "signal_calibration.id asc" in sql
