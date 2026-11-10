"""Unit-wide fixtures: the deterministic fleet and settings bound to a temp calibration path."""

from pathlib import Path

import msgspec
import pytest

from e_jev.infra.settings import Settings
from e_jev.models.systemone import SystemOneRequest
from tests import kit


@pytest.fixture
def reader() -> kit.FakeReader:
    return kit.FakeReader()


@pytest.fixture
def fleet(reader: kit.FakeReader) -> kit.FakeFleet:
    return kit.fleet_of(reader)


@pytest.fixture
def fleet_down() -> kit.FakeFleet:
    return kit.fleet_of(kit.FakeReader(up=False))


@pytest.fixture
def fleet_failing() -> kit.FakeFleet:
    return kit.fleet_of(kit.FailingReader())


@pytest.fixture
def fleet_ratelimited() -> kit.FakeFleet:
    return kit.fleet_of(kit.RateLimitedReader())


@pytest.fixture
def fleet_overloaded() -> kit.FakeFleet:
    return kit.fleet_of(kit.OverloadedReader())


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        JEV_CALIBRATION=tmp_path / "calibration.json", JEV_ENV="dev", JEV_READING_URL="http://reading/v1", JEV_READING_MODEL="m"
    )


@pytest.fixture
def request_systemone(request_bytes: bytes) -> SystemOneRequest:
    return msgspec.json.decode(request_bytes, type=SystemOneRequest)
