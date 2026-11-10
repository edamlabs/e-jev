"""logic/decision/ports: what the decision runner asks of what the root hands it — a fleet and, optionally, an extractor."""

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from e_jev.models.systemone import Json
from e_jev.ports.decide import DecidePort


@runtime_checkable
class FleetView(Protocol):
    """The members by backend id, whether any of them serves, and each one's own answer."""

    @property
    def members(self) -> Mapping[str, DecidePort]: ...

    async def health(self) -> bool: ...

    async def report(self) -> dict[str, bool]: ...


@runtime_checkable
class ExtractView(Protocol):
    """The one capability only a generative teacher keeps: a value generated under a JSON schema."""

    async def extract(self, prompt: str, schema: dict[str, Any]) -> Json: ...
