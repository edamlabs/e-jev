"""api/lifespan/logic: the decision runner over the fleet — calibration loaded, the reading member as the extractor."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from litestar import Litestar

from e_jev.engines.fleet import FleetEngine
from e_jev.infra.settings import Settings
from e_jev.logic.decision.ports import ExtractView
from e_jev.logic.decision.runner import DecisionRunner
from e_jev.models.calibration import Calibration
from e_jev.models.catalog import Backend, BackendName


@asynccontextmanager
async def logic(app: Litestar) -> AsyncIterator[None]:
    st: Settings = app.state.settings
    fleet: FleetEngine = app.state.fleet
    backends: tuple[Backend, ...] = app.state.backends
    reading = fleet.members.get(BackendName.READING)
    app.state.runner = DecisionRunner(
        fleet,
        model=backends[0].model or backends[0].id,
        specs=backends,
        rows=st.JEV_ROWS,
        calibration=Calibration.load(st.JEV_CALIBRATION, st.JEV_PERMUTATIONS),
        extractor=reading if isinstance(reading, ExtractView) else None,
        sink=app.state.sink,
    )
    yield
