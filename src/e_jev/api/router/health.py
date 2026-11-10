"""api/router/health: liveness answers always; readiness while any backend of the fleet answers, naming each one."""

from typing import Final

from litestar import Response, get
from litestar.di import NamedDependency
from litestar.handlers import HTTPRouteHandler
from litestar.status_codes import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from e_jev.logic.decision.runner import DecisionRunner


async def health() -> dict[str, str]:
    return {"status": "ok"}


async def ready(runner: NamedDependency[DecisionRunner]) -> Response[dict[str, object]]:
    members = await runner.report()
    up = any(members.values())
    return Response(
        {"status": "ready" if up else "down", "backends": {name: "up" if live else "down" for name, live in members.items()}},
        status_code=HTTP_200_OK if up else HTTP_503_SERVICE_UNAVAILABLE,
    )


ROUTES: Final[tuple[HTTPRouteHandler, ...]] = (
    get("/health", name="health")(health),
    get("/ready", name="ready")(ready),
)
