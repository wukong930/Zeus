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
