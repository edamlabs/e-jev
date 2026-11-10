"""logic/readout/prompts: questions as lettered readouts — options, orders, the state leading every prompt."""

import pytest

from e_jev.logic.readout.prompts import Readout, orders_readout, prompt_readout, read_question
from e_jev.models.systemone import SystemOneRequest


@pytest.mark.parametrize(
    ("name", "options"),
    [
        ("is_urgent", ("Yes — Explicitly time-sensitive", "No — No urgency expressed")),
        ("department", ("billing — Payments, invoicing, refunds", "technical", "sales — Pricing")),
        ("frustration", ("Calm", "Frustrated", "Very angry")),
    ],
)
async def test_read_question_options(request_systemone: SystemOneRequest, name: str, options: tuple[str, ...]) -> None:
    assert read_question(request_systemone.questions[name]).options == options


async def test_prompt_readout_letters_follow_order() -> None:
    assert prompt_readout("s", Readout(task="Pick.", instructions="q?", options=("yes", "no")), (1, 0)).endswith("Options:\nA. no\nB. yes")


@pytest.mark.parametrize(("permutations", "expected"), [(1, ((0, 1, 2),)), (2, ((0, 1, 2), (2, 1, 0)))])
async def test_orders_readout(permutations: int, expected: tuple[tuple[int, ...], ...]) -> None:
    assert orders_readout(3, permutations) == expected


async def test_prompt_readout_state_leads_every_question_type(request_systemone: SystemOneRequest) -> None:
    prompts = [prompt_readout("STATE", read_question(question), (0, 1)) for question in request_systemone.questions.values()]
    assert all(prompt.startswith("State:\nSTATE\n\n") for prompt in prompts)
