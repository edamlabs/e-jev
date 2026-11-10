"""api/router/extract: POST /v1/extract — typed values from the reading backend, beyond Jev."""

from typing import Final

from litestar import post
from litestar.di import NamedDependency
from litestar.handlers import HTTPRouteHandler

from e_jev.api.security import bearer
from e_jev.logic.decision.runner import DecisionRunner
from e_jev.models.extract import ExtractRequest
from e_jev.models.systemone import Json


async def extract(data: ExtractRequest, runner: NamedDependency[DecisionRunner]) -> Json:
    return await runner.extract(data)


ROUTES: Final[tuple[HTTPRouteHandler, ...]] = (post("/v1/extract", name="extract", guards=[bearer], status_code=200)(extract),)
