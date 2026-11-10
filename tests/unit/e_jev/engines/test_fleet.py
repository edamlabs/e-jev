"""engines/fleet: one backend refusing to open degrades the fleet, it does not sink it — and the backend that returns is
reopened, once per delay."""

from contextlib import AsyncExitStack
from typing import Final

import pytest

from e_jev.engines.fleet import DownFleetEngine, FleetEngine
from e_jev.models.error import RequestError
from e_jev.models.systemone import Noul
from e_jev.ports.decide import DecidePort
from tests import kit


async def _refuse(stack: AsyncExitStack) -> DecidePort:
    message = "connection refused"
    raise OSError(message)


async def test_down_member_raises_through_the_row() -> None:
    down = DownFleetEngine("dead", "connection refused", _refuse)
    assert down.backend == "dead"
    with pytest.raises(RequestError, match="unavailable: connection refused"):
        await down.decide("s", {"q": Noul(instructions="?")})


async def test_down_member_returns_when_the_server_comes_back() -> None:
    live = kit.FakeDecider("dead")

    async def reopen(stack: AsyncExitStack) -> DecidePort:
        return live

    down = DownFleetEngine("dead", "connection refused", reopen, delay=0.0)
    assert await down.health() is True
    decision = await down.decide("s", {"q": Noul(instructions="?")})
    assert (decision.input_tokens, live.seen) == (10, [("q",)])


async def test_down_member_reopens_at_most_once_per_delay() -> None:
    attempts: Final[list[int]] = []

    async def counting(stack: AsyncExitStack) -> DecidePort:
        attempts.append(1)
        return await _refuse(stack)

    down = DownFleetEngine("dead", "refused", counting)
    for _ in range(2):
        with pytest.raises(RequestError):
            await down.health()
    assert len(attempts) == 1


async def test_down_member_keeps_the_freshest_diagnosis() -> None:
    reasons = iter(("HTTP 404: no model", "HTTP 503: busy"))

    async def reopening(stack: AsyncExitStack) -> DecidePort:
        raise RequestError(next(reasons))

    down = DownFleetEngine("dead", "initial", reopening, delay=0.0)
    with pytest.raises(RequestError, match="HTTP 404"):
        await down.health()
    with pytest.raises(RequestError, match="HTTP 503: busy"):
        await down.decide("s", {"q": Noul(instructions="?")})


async def test_down_member_closes_what_it_reopened() -> None:
    live = kit.FakeDecider("dead")
    closed = False

    async def marking() -> None:
        nonlocal closed
        closed = True

    async def reopening(stack: AsyncExitStack) -> DecidePort:
        stack.push_async_callback(marking)
        return live

    down = DownFleetEngine("dead", "down", reopening)
    assert (await down.health(), closed) == (True, False)
    await down.aclose()
    assert closed is True


async def test_down_reader_extracts_once_back(reader: kit.FakeReader) -> None:
    async def reopen(stack: AsyncExitStack) -> DecidePort:
        return kit.fleet_of(reader).members["reading"]

    down = DownFleetEngine("reading", "down", reopen, delay=0.0)
    assert await down.extract("p", {"type": "object"}) == {"schema": ["type"]}


async def test_fleet_survives_a_dead_member() -> None:
    async def live(stack: AsyncExitStack) -> DecidePort:
        return kit.FakeDecider("up")

    async with FleetEngine({"up": live, "dead": _refuse}) as fleet:
        assert isinstance(fleet.members["dead"], DownFleetEngine)
        assert (await fleet.health(), await fleet.report()) == (True, {"up": True, "dead": False})


async def test_fleet_down_when_every_member_is() -> None:
    async with FleetEngine({"dead": _refuse}) as fleet:
        assert await fleet.health() is False
