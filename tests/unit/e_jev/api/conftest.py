"""API fixtures: the real app over the fake fleet, open and closed through its lifespans."""

from collections.abc import AsyncIterator

import pytest
from litestar.testing import AsyncTestClient

from e_jev.infra.settings import Settings
from e_jev.main import create_app
from tests import kit


async def _client(settings: Settings, fleet: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async with AsyncTestClient(app=create_app(settings, lifespans=kit.lifespans_of(fleet))) as client:
        yield client


@pytest.fixture
async def client(settings: Settings, fleet: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async for open_client in _client(settings, fleet):
        yield open_client


@pytest.fixture
async def client_down(settings: Settings, fleet_down: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async for open_client in _client(settings, fleet_down):
        yield open_client


@pytest.fixture
async def client_failing(settings: Settings, fleet_failing: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async for open_client in _client(settings, fleet_failing):
        yield open_client


@pytest.fixture
async def client_ratelimited(settings: Settings, fleet_ratelimited: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async for open_client in _client(settings, fleet_ratelimited):
        yield open_client


@pytest.fixture
async def client_overloaded(settings: Settings, fleet_overloaded: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async for open_client in _client(settings, fleet_overloaded):
        yield open_client


@pytest.fixture
async def client_keyed(settings: Settings, fleet: kit.FakeFleet) -> AsyncIterator[AsyncTestClient]:
    async for open_client in _client(settings.model_copy(update={"JEV_API_KEY": "k"}), fleet):
        yield open_client
