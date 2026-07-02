from dataclasses import asdict
from types import SimpleNamespace

from app.services.governance.appliers import apply_approved_change, register_change_applier


async def test_apply_approved_change_dispatches_to_registered_applier():
    captured = {}

    async def fake(session, row, decided_by):
        captured["decided_by"] = decided_by
        return {"applied": True, "production_effect": "unit_applied"}

    register_change_applier("unit_test_source", fake)
    row = SimpleNamespace(source="unit_test_source", proposed_change={})

    result = await apply_approved_change(None, row, decided_by="alice")

    assert result == {"applied": True, "production_effect": "unit_applied"}
    assert captured["decided_by"] == "alice"


async def test_apply_approved_change_unknown_source_has_no_effect():
    row = SimpleNamespace(source="totally_unknown_source", proposed_change={})
    result = await apply_approved_change(None, row, decided_by="bob")
    assert result["applied"] is False
    assert result["production_effect"] == "none"


async def test_calibration_applier_reconstructs_and_applies_with_approval(monkeypatch):
    from app.services.calibration.governance import apply_calibration_review
    from app.services.calibration.updater import CalibrationProposal

    proposal = CalibrationProposal(
        signal_type="momentum",
        category="ferrous",
        regime="trend",
        base_weight=1.0,
        effective_weight=1.2,
        rolling_hit_rate=0.55,
        sample_size=30,
        hit_count=17,
        miss_count=13,
        alpha_prior=4.0,
        beta_prior=4.0,
        decay_detected=False,
        decay_score=0.1,
        prior_dominant=False,
    )
    proposed_change = {**asdict(proposal), "review_triage": {"tier": "must_review"}}
    captured = {}

    async def fake_apply(session, prop, *, applied_at=None):
        captured["signal_type"] = prop.signal_type
        return SimpleNamespace(id="cal-123")

    monkeypatch.setattr(
        "app.services.calibration.governance.apply_signal_calibration_change", fake_apply
    )
    row = SimpleNamespace(proposed_change=proposed_change)

    result = await apply_calibration_review(None, row, "carol")

    assert result["production_effect"] == "calibration_applied"
    assert result["target_key"] == "momentum:ferrous:trend"
    # approval is structural (this applier only runs on an approved review), so the
    # applier is called with the reconstructed proposal — no human_approved flag.
    assert captured["signal_type"] == "momentum"
    assert captured["signal_type"] == "momentum"


async def test_calibration_applier_incomplete_proposal_has_no_effect():
    from app.services.calibration.governance import apply_calibration_review

    row = SimpleNamespace(proposed_change={"signal_type": "momentum"})  # missing fields
    result = await apply_calibration_review(None, row, "carol")
    assert result["applied"] is False
    assert result["production_effect"] == "none"


async def test_forecast_promotion_applier_emits_authoritative_forecast(monkeypatch):
    from app.services.prediction import governance as fc_gov

    captured = {}

    async def fake_generate(session, *, as_of, decision_grade=False, **kwargs):
        captured["decision_grade"] = decision_grade
        return SimpleNamespace(id="fc-1")

    monkeypatch.setattr(fc_gov, "generate_cross_sectional_forecast", fake_generate)
    row = SimpleNamespace(
        proposed_change={"signal": "xs_reversal_mom120", "model_version": "xs_reversal/1.0"}
    )

    result = await fc_gov.apply_forecast_promotion(None, row, "dave")

    assert result["production_effect"] == "forecast_promoted"
    assert captured["decision_grade"] is True  # promotion makes the forecast authoritative
    assert result["authoritative_forecast_id"] == "fc-1"
