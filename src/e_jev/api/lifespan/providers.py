"""api/lifespan/providers: what the service talks to beside its backends — the trace exporter and the decision log.

The exporter is built with the app (the HTTP plugin needs its provider at construction) and opened here; the log opens
only when JEV_DECISION_LOG names a file."""

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from litestar import Litestar

from e_jev.infra.settings import Settings
from e_jev.providers.drivers.sink.jsonl import JsonlSinkDriver
from e_jev.providers.drivers.telemetry.otlp import OtlpTelemetryDriver


@asynccontextmanager
async def providers(app: Litestar) -> AsyncIterator[None]:
    st: Settings = app.state.settings
    async with AsyncExitStack() as stack:
        telemetry: OtlpTelemetryDriver | None = app.state.telemetry
        match telemetry:
            case None:
                pass
            case driver:
                await stack.enter_async_context(driver)
        app.state.sink = await stack.enter_async_context(JsonlSinkDriver(path=st.JEV_DECISION_LOG)) if st.JEV_DECISION_LOG else None
        yield
