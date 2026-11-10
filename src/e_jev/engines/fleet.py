"""engines/fleet: every selected backend opened as one — a member that refuses to open degrades, it never sinks the fleet.

The composition root hands one opener per backend: given a stack, it enters that backend's providers on it and returns
the member. The fleet opens them all concurrently on its own stack; one that fails is replaced by a down member that
fails every request (the row falls past it) and reopens itself once its server returns — re-opened at most once per
`delay`, so a GPU route stopped by design taxes no decision beyond the delay it waits inside. The engine keeps
references only; what the members acquired is closed with the fleet."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import AsyncExitStack
from types import MappingProxyType
from typing import Any, Final, Protocol, Self, runtime_checkable

from e_jev.infra.logger import logger
from e_jev.models.error import JevError, RequestError
from e_jev.models.systemone import Json, Question
from e_jev.ports.decide import DecidePort, Decision

REOPEN_DELAY: Final = 30.0
REASON: Final = 200

type Opener = Callable[[AsyncExitStack], Awaitable[DecidePort]]


##### TYPES #####
@runtime_checkable
class ExtractMember(Protocol):
    """The one member capability beyond deciding: schema-bound generation (the reading member's)."""

    async def extract(self, prompt: str, schema: dict[str, Any]) -> Json: ...


class DownFleetEngine:
    """A member that refused to open: down until its server returns, then live — no restart owed to a backend that came back."""

    __slots__ = ("_delay", "_live", "_lock", "_next", "_open", "_reason", "backend")

    def __init__(self, backend: str, reason: str, opener: Opener, *, delay: float = REOPEN_DELAY) -> None:
        self.backend = backend
        self._reason = reason
        self._open = opener
        self._delay = delay
        self._live: tuple[DecidePort, AsyncExitStack] | None = None
        self._lock = asyncio.Lock()
        self._next = 0.0

    ##### PRIVATE #####

    async def _common_renew(self) -> DecidePort | None:
        """The live member once the server returns; a failed attempt keeps its fresh diagnosis and waits out the delay."""
        async with self._lock:
            match self._live, time.monotonic() < self._next:
                case (member, _), _:
                    return member
                case None, True:
                    return None
                case None, False:
                    self._next = time.monotonic() + self._delay
                    stack = AsyncExitStack()
                    try:
                        member = await self._open(stack)
                    except (JevError, OSError) as error:
                        await stack.aclose()
                        self._reason = str(error)[:REASON]
                        return None
                    self._live = (member, stack)
                    logger.info("backend recovered", backend=self.backend)
                    return member

    ############################################################

    ##### PUBLIC #####

    async def decide(self, state: str, questions: Mapping[str, Question]) -> Decision:
        match await self._common_renew():
            case None:
                message = f"backend {self.backend} unavailable: {self._reason}"
                raise RequestError(message)
            case live:
                return await live.decide(state, questions)

    async def health(self) -> bool:
        match await self._common_renew():
            case None:
                message = f"backend {self.backend} unavailable: {self._reason}"
                raise RequestError(message)
            case live:
                return await live.health()

    async def extract(self, prompt: str, schema: dict[str, Any]) -> Json:
        """The live member's extraction once it is back; while down, the reason — a gateway failure, never a missing capability."""
        match await self._common_renew():
            case ExtractMember() as live:
                return await live.extract(prompt, schema)
            case _:
                message = f"backend {self.backend} unavailable for extraction: {self._reason}"
                raise RequestError(message)

    async def aclose(self) -> None:
        """Release what a reopen acquired: the fleet's stack calls this on exit."""
        async with self._lock:
            match self._live:
                case (_, stack):
                    await stack.aclose()
                    self._live = None
                case None:
                    return


class FleetEngine:
    """The fleet: members by backend id, in preference order. Ready while any member serves."""

    __slots__ = ("_delay", "_members", "_openers", "_stack")

    def __init__(self, openers: Mapping[str, Opener], *, delay: float = REOPEN_DELAY) -> None:
        self._openers = dict(openers)
        self._delay = delay
        self._stack = AsyncExitStack()
        self._members: Mapping[str, DecidePort] = MappingProxyType({})

    ##### PRIVATE #####

    async def _aenter_member(self, backend: str, opener: Opener) -> DecidePort:
        try:
            return await opener(self._stack)
        except (JevError, OSError) as error:
            logger.warning("backend unavailable", backend=backend, error=str(error)[:REASON])
            down = DownFleetEngine(backend, str(error)[:REASON], opener, delay=self._delay)
            self._stack.push_async_callback(down.aclose)
            return down

    @staticmethod
    async def _health_member(member: DecidePort) -> bool:
        try:
            return await member.health()
        except JevError, OSError:
            return False

    ############################################################

    ##### PUBLIC #####

    async def __aenter__(self) -> Self:
        members = await asyncio.gather(*(self._aenter_member(backend, opener) for backend, opener in self._openers.items()))
        self._members = MappingProxyType(dict(zip(self._openers, members, strict=True)))
        logger.info("fleet opened", backends=list(self._members))
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._stack.aclose()

    @property
    def members(self) -> Mapping[str, DecidePort]:
        return self._members

    async def health(self) -> bool:
        """Ready while any member serves: the fleet degrades, it does not all have to stand."""
        return any(await asyncio.gather(*(self._health_member(member) for member in self._members.values())))

    async def report(self) -> dict[str, bool]:
        """Each member's own answer, for `/ready` to name who is down."""
        states = await asyncio.gather(*(self._health_member(member) for member in self._members.values()))
        return dict(zip(self._members, states, strict=True))
