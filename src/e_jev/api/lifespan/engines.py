"""api/lifespan/engines: the fleet — every selected catalog backend, resolved from the settings and opened as one.

`JEV_BACKENDS` names catalog entries; each becomes a `Backend` with what the deployment decides (URL, key, served
model) filled from the settings, and an opener from the frozen table below: the reading kind opens the readout driver
and reads through it, a systemone kind is the driver itself. A selected backend whose endpoint is unset stops the start
here, naming the variable — the CLI shares these openers to calibrate a backend through the very path it serves on."""

from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from types import MappingProxyType
from typing import Final

from litestar import Litestar

from e_jev.engines.fleet import FleetEngine, Opener
from e_jev.infra.settings import Settings
from e_jev.logic.readout.decider import ReadoutDecider
from e_jev.logic.readout.labels import UNIVERSE
from e_jev.models.catalog import CATALOG, Backend, BackendKind, BackendName
from e_jev.models.error import MissingEndpointError
from e_jev.ports.decide import DecidePort
from e_jev.providers.drivers.decide.systemone import SystemOneDecideDriver
from e_jev.providers.drivers.readout.vllm import VllmReadoutDriver


##### OPENERS #####
def open_reading(backend: Backend, st: Settings) -> Opener:
    async def opener(stack: AsyncExitStack) -> DecidePort:
        reader = await stack.enter_async_context(
            VllmReadoutDriver(
                url=backend.url,
                api_key=backend.api_key,
                model=backend.model,
                universe=UNIVERSE,
                extract_tokens=st.JEV_EXTRACT_MAX_TOKENS,
                priority=st.JEV_READING_PRIORITY,
                timeout=backend.timeout,
            )
        )
        return ReadoutDecider(
            reader, backend=backend.id, permutations=st.JEV_PERMUTATIONS, concurrency=backend.concurrency, epsilon=st.JEV_TRIE_EPSILON
        )

    return opener


def open_systemone(backend: Backend, _st: Settings) -> Opener:
    async def opener(stack: AsyncExitStack) -> DecidePort:
        return await stack.enter_async_context(
            SystemOneDecideDriver(
                backend=backend.id,
                url=backend.url,
                api_key=backend.api_key,
                model=backend.model,
                concurrency=backend.concurrency,
                timeout=backend.timeout,
            )
        )

    return opener


OPENERS: Final[Mapping[BackendKind, Callable[[Backend, Settings], Opener]]] = MappingProxyType(
    {
        BackendKind.READING: open_reading,
        BackendKind.SYSTEMONE: open_systemone,
    }
)


##### RESOLUTION #####
def resolve(st: Settings) -> tuple[Backend, ...]:
    """Every selected catalog entry with the deployment's endpoint filled in; an endpoint left unset refuses to start."""
    deployed = {
        BackendName.READING: {
            "url": st.JEV_READING_URL,
            "api_key": st.JEV_READING_KEY,
            "model": st.JEV_READING_MODEL,
            "max_state_tokens": st.JEV_READING_MAX_STATE_TOKENS,
        },
        BackendName.SYSTEMONE: {"url": st.JEV_SYSTEMONE_URL, "api_key": st.JEV_SYSTEMONE_KEY, "model": st.JEV_SYSTEMONE_MODEL},
        BackendName.H2O_LIGHTNING_4B: {"url": st.JEV_H2O_URL},
        BackendName.CLEF_FLASH: {"url": st.JEV_CLEF_URL},
    }
    required = {BackendName.READING: ("JEV_READING_URL", "JEV_READING_MODEL"), BackendName.SYSTEMONE: ("JEV_SYSTEMONE_URL",)}
    unset = ((name, tuple(variable for variable in required.get(name, ()) if not getattr(st, variable))) for name in st.JEV_BACKENDS)
    match next(((name, missing) for name, missing in unset if missing), None):
        case (name, missing):
            raise MissingEndpointError(name, missing)
        case None:
            pass
    return tuple(replace(CATALOG[name], **deployed[name]) for name in dict.fromkeys(st.JEV_BACKENDS))


def openers(backends: tuple[Backend, ...], st: Settings) -> dict[str, Opener]:
    return {backend.id: OPENERS[backend.kind](backend, st) for backend in backends}


##### LIFESPAN #####
@asynccontextmanager
async def engines(app: Litestar) -> AsyncIterator[None]:
    st: Settings = app.state.settings
    backends = resolve(st)
    async with FleetEngine(openers(backends, st)) as fleet:
        app.state.backends = backends
        app.state.fleet = fleet
        yield
