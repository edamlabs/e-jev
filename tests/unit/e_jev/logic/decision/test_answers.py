"""logic/decision/answers: calibrated distributions as TypeSafe's typed answers, confidence by the reference formulas."""

import msgspec
import numpy as np
import pytest
from typesafe_sdk._core.response_types import SystemOneResponse as SdkResponse

from e_jev.logic.decision.answers import build_answer, confidence_choice, confidence_score, index_label
from e_jev.models.error import LabelIndexError
from e_jev.models.systemone import SystemOneRequest, SystemOneResponse, Usage


async def test_build_answer_validates_against_official_sdk(request_systemone: SystemOneRequest) -> None:
    probs = {"is_urgent": [0.95, 0.05], "department": [0.1, 0.85, 0.05], "frustration": [0.0, 0.95, 0.05]}
    response = SystemOneResponse(
        model="m",
        answers={name: build_answer(question, np.array(probs[name])) for name, question in request_systemone.questions.items()},
        usage=Usage(input_tokens=300, output_tokens=3),
    )
    parsed = SdkResponse.model_validate_json(msgspec.json.encode(response))
    assert (parsed.nouls["is_urgent"].noul, parsed.choices["department"].choice, parsed.scores["frustration"].score) == pytest.approx(
        (0.95, "technical", 1.05)
    )
    assert parsed.scores["frustration"].legend[2] == "Very angry"


@pytest.mark.parametrize(("probs", "expected"), [([0.5, 0.5], 0.0), ([1.0, 0.0, 0.0], 1.0), ([0.88, 0.12, 0.0], 0.82)])
async def test_confidence_choice_matches_reference(probs: list[float], expected: float) -> None:
    assert confidence_choice(np.array(probs)) == pytest.approx(expected)


@pytest.mark.parametrize(("probs", "expected"), [([1 / 3] * 3, 0.0), ([0.0, 1.0, 0.0], 1.0), ([0.0, 0.95, 0.05], 0.925)])
async def test_confidence_score_matches_reference(probs: list[float], expected: float) -> None:
    assert confidence_score(np.array(probs)) == pytest.approx(expected)


@pytest.mark.parametrize(("name", "label", "index"), [("is_urgent", "FALSE", 1), ("department", "sales", 2), ("frustration", "1", 1)])
async def test_index_label(request_systemone: SystemOneRequest, name: str, label: str, index: int) -> None:
    assert index_label(request_systemone.questions[name], label) == index


@pytest.mark.parametrize(("name", "label"), [("is_urgent", "maybe"), ("department", "legal"), ("frustration", "3")])
async def test_index_label_unknown(request_systemone: SystemOneRequest, name: str, label: str) -> None:
    with pytest.raises(LabelIndexError):
        index_label(request_systemone.questions[name], label)
