import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.learning import validate_learning_hypothesis, vector_shadow_candidate_config
from app.core.database import get_db
from app.main import create_app
from app.models.change_review_queue import ChangeReviewQueue
from app.models.drift_metrics import DriftMetric
from app.models.learning_hypotheses import LearningHypothesis
from app.models.recommendation import Recommendation
from app.models.shadow_runs import ShadowRun
from app.models.signal import SignalTrack
from app.models.user_feedback import UserFeedback
from app.models.vector_chunks import VectorChunk
from app.models.vector_eval_set import VectorEvalCase
from app.services.calibration.updater import CalibrationProposal, apply_signal_calibration_change
from app.services.governance.review_queue import ReviewRequiredError
from app.services.learning.reflection_agent import (
    LearningHypothesisCandidate,
    parse_reflection_candidates,
    persist_learning_hypotheses,
    run_reflection_agent,
)
from app.services.llm.types import LLMCompletionResult
from app.services.vector_search.eval import compare_vector_search_candidate, evaluate_single_case
from app.services.vector_search.eval_seed import seed_vector_eval_cases
from app.services.vector_search.hybrid_search import VectorSearchResult, quality_weight


def test_learning_api_bounds_query_text_fields() -> None:
    async def fake_db():
        yield object()

    app = create_app()
    app.dependency_overrides[get_db] = fake_db
    client = TestClient(app)
    hypothesis_id = uuid4()

    cases = (
        ("get", f"/api/learning/hypotheses?status_filter={'x' * 21}"),
        (
            "post",
            f"/api/learning/hypotheses/{hypothesis_id}/approve-shadow?reviewed_by={'x' * 81}",
        ),
        (
            "post",
            f"/api/learning/hypotheses/{hypothesis_id}/reject?reason={'x' * 4001}",
        ),
        (
            "post",
            f"/api/learning/hypotheses/{hypothesis_id}/apply?approved_by={'x' * 81}",
        ),
        (
            "get",
            f"/api/learning/vector-eval/shadow-compare?candidate_name={'x' * 121}"
            "&candidate_alpha=0.7",
        ),
        ("post", f"/api/learning/vector-eval/seed?reviewed_by={'x' * 81}"),
    )

    for method, path in cases:
        response = getattr(client, method)(path)
        assert response.status_code == 422


class FakeScalars:
    def __init__(self, rows: list | None = None, first_row=None) -> None:
        self._rows = rows or []
        self._first_row = first_row

    def all(self) -> list:
        return self._rows

    def first(self):
        return self._first_row


class FakeSession:
    def __init__(
        self,
        scalar_batches: list[list] | None = None,
        scalar_values: list[int] | None = None,
    ) -> None:
        self.scalar_batches = scalar_batches or []
        self.scalar_values = scalar_values or []
        self.scalar_statements: list[object] = []
        self.scalar_value_statements: list[object] = []
        self.rows: list[object] = []
        self.flush_count = 0

    async def scalars(self, statement) -> FakeScalars:
        self.scalar_statements.append(statement)
        if self.scalar_batches:
            return FakeScalars(rows=self.scalar_batches.pop(0))
        return FakeScalars()

    async def scalar(self, statement):
        self.scalar_value_statements.append(statement)
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return 0

    def add(self, row: object) -> None:
        self.rows.append(row)

    async def flush(self) -> None:
        self.flush_count += 1


class FakeLearningValidationSession:
    def __init__(self, hypothesis: LearningHypothesis, shadow_run: ShadowRun) -> None:
        self.hypothesis = hypothesis
        self.shadow_run = shadow_run

    async def get(self, model, _):
        if model is LearningHypothesis:
            return self.hypothesis
        if model is ShadowRun:
            return self.shadow_run
        return None


def test_parse_reflection_candidates_requires_pydantic_shape() -> None:
    candidates = parse_reflection_candidates(
        json.dumps(
            {
                "hypotheses": [
                    {
                        "hypothesis": "Momentum underperforms after high-volatility regime flips.",
                        "supporting_evidence": ["momentum misses clustered in range_high_vol"],
                        "proposed_change": "Review momentum confidence threshold in range_high_vol.",
                        "confidence": 0.62,
                        "counterevidence_considered": [
                            "small sample may be noise",
                            "inventory shocks overlap with the same period",
                        ],
                        "sample_size": 42,
                    },
                    {"hypothesis": "too short"},
                ]
            }
        )
    )

    assert len(candidates) == 1
    assert candidates[0].sample_size == 42


async def test_reflection_hypotheses_are_gated_and_review_queued() -> None:
    session = FakeSession()
    candidates = [
        LearningHypothesisCandidate(
            hypothesis="Momentum underperforms after high-volatility regime flips.",
            supporting_evidence=["miss cluster in range_high_vol"],
            proposed_change="Review momentum confidence threshold in range_high_vol.",
            confidence=0.62,
            counterevidence_considered=["sample noise", "overlapping news shocks"],
            sample_size=42,
        ),
        LearningHypothesisCandidate(
            hypothesis="News severity should be automatically lowered immediately.",
            supporting_evidence=["several missed alerts"],
            proposed_change="自动修改 news_event 阈值。",
            confidence=0.7,
            counterevidence_considered=["sample noise", "manual labels changed"],
            sample_size=55,
        ),
        LearningHypothesisCandidate(
            hypothesis="Rubber signals changed behavior after delivery month.",
            supporting_evidence=["two observations"],
            proposed_change="Review rubber signal diagnostics.",
            confidence=0.5,
            counterevidence_considered=["seasonal effect", "calendar spread noise"],
            sample_size=12,
        ),
    ]

    result = await persist_learning_hypotheses(
        session,  # type: ignore[arg-type]
        candidates,
        source_payload={"model": "fake"},
    )

    hypotheses = [row for row in session.rows if isinstance(row, LearningHypothesis)]
    reviews = [row for row in session.rows if isinstance(row, ChangeReviewQueue)]
    chunks = [row for row in session.rows if isinstance(row, VectorChunk)]
    assert result.generated == 3
    assert result.proposed == 2
    assert result.rejected == 1
    assert result.weak_evidence == 1
    assert len(reviews) == 2
    assert hypotheses[1].status == "rejected"
    assert hypotheses[1].rejection_reason == "unsafe_auto_apply_language"
    assert len(chunks) == 3
    assert all(chunk.quality_status == "unverified" for chunk in chunks)


async def test_run_reflection_agent_sends_sanitized_relative_payload() -> None:
    now = datetime(2026, 5, 4, tzinfo=timezone.utc)
    session = FakeSession(
        scalar_batches=[
            [
                SignalTrack(
                    signal_type="momentum",
                    category="ferrous",
                    confidence=0.75,
                    outcome="miss",
                    forward_return_5d=-0.03,
                    created_at=now,
                )
            ],
            [
                Recommendation(
                    status="completed",
                    recommended_action="open_spread",
                    legs=[{"asset": "RB", "direction": "long"}],
                    priority_score=80,
                    portfolio_fit_score=70,
                    margin_efficiency_score=75,
                    margin_required=100000,
                    reasoning="test",
                    expires_at=now + timedelta(days=1),
                    actual_entry=100,
                    actual_exit=106,
                    created_at=now,
                )
            ],
            [UserFeedback(signal_type="momentum", agree="disagree", will_trade="will_not_trade")],
            [DriftMetric(metric_type="signal_hit_rate", drift_severity="yellow", computed_at=now)],
        ]
    )

    async def fake_completer(**kwargs):
        user_payload = json.loads(kwargs["options"].messages[1].content)
        encoded = json.dumps(user_payload)
        assert "margin_required" not in encoded
        assert "pnl_realized" not in encoded
        assert user_payload["recommendations"][0]["relative_return"] == 0.06
        return LLMCompletionResult(
            content=json.dumps(
                {
                    "hypotheses": [
                        {
                            "hypothesis": "Momentum misses rose in ferrous during recent drift.",
                            "supporting_evidence": ["missed signal", "yellow drift"],
                            "proposed_change": "Review momentum gating in ferrous.",
                            "confidence": 0.6,
                            "counterevidence_considered": ["small sample", "single sector"],
                            "sample_size": 31,
                        }
                    ]
                }
            ),
            model="fake-reflector",
        )

    result = await run_reflection_agent(
        session,  # type: ignore[arg-type]
        as_of=now,
        completer=fake_completer,
    )

    assert result.proposed == 1
    assert any(isinstance(row, ChangeReviewQueue) for row in session.rows)


async def test_proposed_hypothesis_cannot_modify_calibration_without_review() -> None:
    session = FakeSession()
    proposal = CalibrationProposal(
        signal_type="momentum",
        category="ferrous",
        regime="range_high_vol",
        base_weight=1.0,
        effective_weight=0.8,
        rolling_hit_rate=0.45,
        sample_size=42,
        hit_count=19,
        miss_count=23,
        alpha_prior=4.0,
        beta_prior=4.0,
        decay_detected=True,
        decay_score=3.2,
        prior_dominant=False,
    )

    with pytest.raises(ReviewRequiredError):
        await apply_signal_calibration_change(
            session,  # type: ignore[arg-type]
            proposal,
            review_source="llm_agent",
            target_key="proposed-hypothesis",
            proposed_change=proposal.to_change(),
        )

    assert isinstance(session.rows[0], ChangeReviewQueue)


async def test_validate_hypothesis_rejects_unlinked_shadow_run() -> None:
    hypothesis_id = uuid4()
    hypothesis = LearningHypothesis(
        id=hypothesis_id,
        hypothesis="Review momentum threshold after drift.",
        supporting_evidence=[],
        status="shadow_testing",
    )
    shadow_run = ShadowRun(
        id=uuid4(),
        name="other-hypothesis-shadow",
        algorithm_version="llm-reflection-shadow",
        config_diff={"source_hypothesis_id": str(uuid4())},
        status="active",
        started_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )
    session = FakeLearningValidationSession(hypothesis, shadow_run)

    with pytest.raises(HTTPException) as exc:
        await validate_learning_hypothesis(
            hypothesis_id,
            shadow_run.id,
            min_hit_rate_delta=0.0,
            max_disagreement_rate=0.35,
            session=session,  # type: ignore[arg-type]
        )

    assert exc.value.status_code == 409
    assert "not linked" in exc.value.detail


def test_vector_eval_metrics_and_quality_weights_are_active() -> None:
    relevant_a = uuid4()
    relevant_b = uuid4()
    irrelevant = uuid4()
    case = VectorEvalCase(
        id=uuid4(),
        query_text="rubber supply shock",
        relevant_chunk_ids=[str(relevant_a), str(relevant_b)],
    )
    retrieved = [
        _result(irrelevant, "validated"),
        _result(relevant_b, "human_reviewed"),
        _result(relevant_a, "unverified"),
    ]

    result = evaluate_single_case(case, retrieved)

    assert result.hits == 2
    assert result.recall_at_10 == 1.0
    assert 0 < result.ndcg_at_10 < 1
    assert quality_weight("unverified") == 0.5
    assert quality_weight("human_reviewed") == 1.0
    assert quality_weight("validated") == 1.2


async def test_vector_eval_seed_creates_fifty_query_pairs() -> None:
    chunks = [
        VectorChunk(
            id=uuid4(),
            chunk_type="news",
            content_text=f"rubber supply disruption sample {index}",
            metadata_json={"symbol": "RU"},
            quality_status="human_reviewed",
        )
        for index in range(3)
    ]
    session = FakeSession(scalar_batches=[chunks, []], scalar_values=[0])

    result = await seed_vector_eval_cases(
        session,  # type: ignore[arg-type]
        target_cases=50,
        reviewed_by="tester",
    )

    cases = [row for row in session.rows if isinstance(row, VectorEvalCase)]
    assert result.existing_cases == 0
    assert result.created == 50
    assert len(cases) == 50
    assert all(case.relevant_chunk_ids for case in cases)


async def test_vector_eval_seed_checks_only_candidate_query_texts() -> None:
    chunk = VectorChunk(
        id=uuid4(),
        chunk_type="news",
        content_text="rubber supply disruption sample",
        metadata_json={"symbol": "RU"},
        quality_status="human_reviewed",
    )
    session = FakeSession(
        scalar_batches=[[chunk], ["RU upstream driver #01"]],
        scalar_values=[7],
    )

    result = await seed_vector_eval_cases(
        session,  # type: ignore[arg-type]
        target_cases=1,
        reviewed_by="tester",
    )

    assert result.existing_cases == 7
    assert result.created == 0
    assert session.rows == []
    assert "vector_eval_set.query_text" in str(session.scalar_statements[1])


async def test_vector_shadow_comparison_reports_candidate_delta() -> None:
    relevant = uuid4()
    case = VectorEvalCase(
        id=uuid4(),
        query_text="rubber supply shock",
        relevant_chunk_ids=[str(relevant)],
    )
    session = FakeSession(scalar_batches=[[case], [case]])

    async def baseline_searcher(*_, **__):
        return [_result(uuid4(), "human_reviewed"), _result(relevant, "human_reviewed")]

    async def candidate_searcher(*_, **__):
        return [_result(relevant, "human_reviewed")]

    comparison = await compare_vector_search_candidate(
        session,  # type: ignore[arg-type]
        candidate_name="bge-m3-candidate",
        baseline_searcher=baseline_searcher,
        candidate_searcher=candidate_searcher,
        candidate_config={"alpha": 0.75},
    )

    assert comparison.ndcg_delta > 0
    assert comparison.recall_delta == 0
    assert comparison.passed_gate is True
    assert comparison.candidate_config == {"alpha": 0.75}


async def test_vector_shadow_comparison_requires_candidate_searcher() -> None:
    with pytest.raises(ValueError, match="candidate_searcher is required"):
        await compare_vector_search_candidate(
            FakeSession(),  # type: ignore[arg-type]
            candidate_name="missing-candidate",
        )


async def test_vector_shadow_comparison_requires_observed_metric_delta_by_default() -> None:
    relevant = uuid4()
    case = VectorEvalCase(
        id=uuid4(),
        query_text="rubber supply shock",
        relevant_chunk_ids=[str(relevant)],
    )
    session = FakeSession(scalar_batches=[[case], [case]])

    async def same_searcher(*_, **__):
        return [_result(relevant, "human_reviewed")]

    comparison = await compare_vector_search_candidate(
        session,  # type: ignore[arg-type]
        candidate_name="same-ranking",
        baseline_searcher=same_searcher,
        candidate_searcher=same_searcher,
        candidate_config={"beta": 0.4},
    )

    assert comparison.ndcg_delta == 0
    assert comparison.recall_delta == 0
    assert comparison.passed_gate is False


def test_vector_shadow_candidate_config_requires_real_delta() -> None:
    with pytest.raises(HTTPException) as missing:
        vector_shadow_candidate_config()

    with pytest.raises(HTTPException) as unchanged:
        vector_shadow_candidate_config(alpha=0.6)

    assert missing.value.status_code == 400
    assert unchanged.value.status_code == 400
    assert vector_shadow_candidate_config(alpha=0.7) == {"alpha": 0.7}


def _result(chunk_id, quality_status: str) -> VectorSearchResult:
    return VectorSearchResult(
        id=chunk_id,
        chunk_type="news",
        source_id=None,
        content_text="sample",
        metadata={},
        quality_status=quality_status,
        final_score=1.0,
        cosine_score=1.0,
        text_score=0.0,
        time_decay=1.0,
        created_at=datetime(2026, 5, 4, tzinfo=timezone.utc),
    )
