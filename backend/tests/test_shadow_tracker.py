from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.alert import Alert
from app.models.signal import SignalTrack
from app.services.calibration.shadow_tracker import (
    alert_to_signal_payload,
    apply_outcome,
    evaluate_pending_signals,
    load_forward_market_data,
    primary_symbol,
)
from app.services.signals.types import MarketBar, OutcomeEvaluation


class FakeScalars:
    def __init__(self, rows: list[SignalTrack]) -> None:
        self._rows = rows

    def all(self) -> list[SignalTrack]:
        return self._rows


class FakeSession:
    def __init__(self, rows: list[SignalTrack], alert: Alert) -> None:
        self.rows = rows
        self.alert = alert
        self.flush_count = 0

    async def scalars(self, _) -> FakeScalars:
        return FakeScalars(self.rows)

    async def get(self, _, __):
        return self.alert

    async def flush(self) -> None:
        self.flush_count += 1


def _bars() -> list[MarketBar]:
    start = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return [
        MarketBar(
            timestamp=start + timedelta(days=idx),
            open=100 + idx,
            high=101 + idx,
            low=99 + idx,
            close=100 + idx,
            volume=100,
        )
        for idx in range(25)
    ]


class FakeMarketRow:
    def __init__(self, timestamp: datetime, close: float) -> None:
        self.timestamp = timestamp
        self.open = close
        self.high = close + 1
        self.low = close - 1
        self.close = close
        self.volume = 100
        self.open_interest = 200


def test_alert_to_signal_payload_uses_alert_and_track_metadata() -> None:
    track = SignalTrack(signal_type="momentum", category="ferrous", confidence=0.8)
    alert = Alert(
        title="RB bullish momentum",
        summary="RB generated a bullish signal.",
        severity="medium",
        category="ferrous",
        type="momentum",
        triggered_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        confidence=0.8,
        related_assets=["RB"],
        risk_items=["Bullish moving-average crossover."],
        manual_check_items=[],
        trigger_chain=[],
    )

    payload = alert_to_signal_payload(alert, track)

    assert payload["signal_type"] == "momentum"
    assert payload["related_assets"] == ["RB"]
    assert primary_symbol(payload) == "RB"


def test_apply_outcome_updates_signal_track() -> None:
    track = SignalTrack(signal_type="momentum", category="ferrous", confidence=0.8)
    resolved_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    apply_outcome(
        track,
        OutcomeEvaluation(
            outcome="hit",
            reason="ok",
            horizon_days=20,
            forward_return_1d=0.01,
            forward_return_5d=0.05,
            forward_return_20d=0.2,
        ),
        resolved_at=resolved_at,
    )

    assert track.outcome == "hit"
    assert track.forward_return_20d == 0.2
    assert track.resolved_at == resolved_at


async def test_evaluate_pending_signals_marks_due_signal_hit(monkeypatch) -> None:
    alert_id = uuid4()
    created_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    track = SignalTrack(
        alert_id=alert_id,
        signal_type="momentum",
        category="ferrous",
        confidence=0.8,
        outcome="pending",
        created_at=created_at,
    )
    alert = Alert(
        id=alert_id,
        title="RB bullish momentum",
        summary="RB generated a bullish signal.",
        severity="medium",
        category="ferrous",
        type="momentum",
        triggered_at=created_at,
        confidence=0.8,
        related_assets=["RB"],
        risk_items=["Bullish moving-average crossover."],
        manual_check_items=[],
        trigger_chain=[],
    )
    session = FakeSession([track], alert)

    async def fake_load_forward_market_data(*_, **__) -> list[MarketBar]:
        return _bars()

    monkeypatch.setattr(
        "app.services.calibration.shadow_tracker.load_forward_market_data",
        fake_load_forward_market_data,
    )

    result = await evaluate_pending_signals(
        session,  # type: ignore[arg-type]
        as_of=created_at + timedelta(days=30),
    )

    assert result.scanned == 1
    assert result.resolved == 1
    assert track.outcome == "hit"
    assert track.forward_return_20d is not None
    assert session.flush_count == 1


async def test_load_forward_market_data_uses_pit_as_of(monkeypatch) -> None:
    captured: dict = {}
    start_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    end_at = start_at + timedelta(days=20)
    as_of = end_at + timedelta(hours=2)

    async def fake_get_market_data_pit(*_, **kwargs):
        captured.update(kwargs)
        return [FakeMarketRow(start_at, 100), FakeMarketRow(end_at, 120)]

    monkeypatch.setattr(
        "app.services.calibration.shadow_tracker.get_market_data_pit",
        fake_get_market_data_pit,
    )

    rows = await load_forward_market_data(
        object(),  # type: ignore[arg-type]
        signal={"related_assets": ["RB"]},
        start_at=start_at,
        end_at=end_at,
        as_of=as_of,
    )

    assert captured["symbol"] == "RB"
    assert captured["start"] == start_at
    assert captured["end"] == end_at
    assert captured["as_of"] == as_of
    assert [row.close for row in rows] == [100, 120]
