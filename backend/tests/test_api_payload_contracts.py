from pydantic import ValidationError

import pytest

from app.api.risk import StressRequest, StressScenarioPayload
from app.api.scenarios import ScenarioSimulationPayload
from app.api.shadow import ShadowRunCreate


def test_local_api_write_payloads_reject_unknown_fields() -> None:
    cases = (
        (
            StressScenarioPayload,
            {
                "name": "oil shock",
                "description": "stress crude",
                "shocks": {"SC": -0.05},
                "shockz": {"SC": -0.1},
            },
        ),
        (
            StressRequest,
            {
                "scenarios": [
                    {
                        "name": "oil shock",
                        "description": "stress crude",
                        "shocks": {"SC": -0.05},
                    }
                ],
                "scenarioz": [],
            },
        ),
        (
            ScenarioSimulationPayload,
            {
                "target_symbol": "SC",
                "shocks": {"SC": -0.05},
                "simulationz": 500,
            },
        ),
        (
            ShadowRunCreate,
            {
                "name": "threshold shadow",
                "algorithm_version": "phase9",
                "config_dif": {"notify": 0.7},
            },
        ),
    )

    for schema, payload in cases:
        with pytest.raises(ValidationError):
            schema.model_validate(payload)


def test_shadow_run_payload_rejects_oversized_config_diff() -> None:
    with pytest.raises(ValidationError):
        ShadowRunCreate.model_validate(
            {
                "name": "threshold shadow",
                "algorithm_version": "phase9",
                "config_diff": {f"key_{index}": index for index in range(33)},
            }
        )


def test_shadow_run_payload_rejects_deep_config_diff() -> None:
    with pytest.raises(ValidationError):
        ShadowRunCreate.model_validate(
            {
                "name": "threshold shadow",
                "algorithm_version": "phase9",
                "config_diff": {
                    "nested": {
                        "a": {
                            "b": {
                                "c": {
                                    "d": {
                                        "e": {
                                            "f": "too deep",
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
            }
        )


def test_shadow_run_payload_rejects_non_json_config_values() -> None:
    with pytest.raises(ValidationError):
        ShadowRunCreate.model_validate(
            {
                "name": "threshold shadow",
                "algorithm_version": "phase9",
                "config_diff": {"bad": object()},
            }
        )


def test_shadow_run_payload_bounds_database_sized_text_fields() -> None:
    with pytest.raises(ValidationError):
        ShadowRunCreate.model_validate(
            {
                "name": "threshold shadow",
                "algorithm_version": "phase9",
                "created_by": "x" * 81,
            }
        )

    with pytest.raises(ValidationError):
        ShadowRunCreate.model_validate(
            {
                "name": "threshold shadow",
                "algorithm_version": "phase9",
                "notes": "x" * 4001,
            }
        )
