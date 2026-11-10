"""e-jev entrypoint: the composition root of the service — the only module that knows the whole app.

Routers enter by explicit registration; the lifespans open, in order, what the service talks to (trace exporter,
decision log), the fleet of catalog backends, and the decision runner over it. Granian calls `create_app` per worker.
"""

import logging
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Final

from litestar import Litestar
from litestar.datastructures import State
from litestar.plugins.opentelemetry import OpenTelemetryConfig, OpenTelemetryPlugin

from e_jev.api.deps import DEPENDENCIES
from e_jev.api.handlers import HANDLERS
from e_jev.api.lifespan.engines import engines
from e_jev.api.lifespan.logic import logic
from e_jev.api.lifespan.providers import providers
from e_jev.api.middlewares import MIDDLEWARES
from e_jev.api.router import extract, health, systemone
from e_jev.infra.logger import setup
from e_jev.infra.settings import Settings
from e_jev.infra.settings import settings as st
from e_jev.providers.drivers.telemetry.otlp import OtlpTelemetryDriver

type Lifespan = Callable[[Litestar], AbstractAsyncContextManager[None]]

LIFESPANS: Final[tuple[Lifespan, ...]] = (providers, engines, logic)


def create_app(settings: Settings = st, *, lifespans: Sequence[Lifespan] = LIFESPANS) -> Litestar:
    setup(env=settings.JEV_ENV, level=logging.getLevelNamesMapping()[settings.JEV_LOG_LEVEL])
    telemetry = (
        OtlpTelemetryDriver(endpoint=settings.JEV_OTLP_ENDPOINT, project=settings.JEV_OTLP_PROJECT) if settings.JEV_OTLP_ENDPOINT else None
    )
    return Litestar(
        route_handlers=[*health.ROUTES, *systemone.ROUTES, *extract.ROUTES],
        lifespan=list(lifespans),
        dependencies=DEPENDENCIES,
        middleware=list(MIDDLEWARES),
        exception_handlers=HANDLERS,
        state=State({"settings": settings, "telemetry": telemetry}),
        plugins=[OpenTelemetryPlugin(OpenTelemetryConfig(tracer_provider=telemetry.provider))] if telemetry else [],
    )
