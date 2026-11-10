"""api/router/systemone: POST /v1/systemone and GET /v1/models — the TypeSafe surface."""

from datetime import date
from typing import Final

from litestar import get, post
from litestar.di import NamedDependency
from litestar.handlers import HTTPRouteHandler

from e_jev.api.security import bearer
from e_jev.infra.settings import Settings
from e_jev.logic.decision.runner import DecisionRunner
from e_jev.models.catalog import Backend
from e_jev.models.systemone import ModelList, ModelMetadata, SystemOneRequest, SystemOneResponse

RELEASED: Final = date(2026, 11, 10).isoformat()


async def evaluate(data: SystemOneRequest, runner: NamedDependency[DecisionRunner]) -> SystemOneResponse:
    return await runner.evaluate(data)


async def models(settings: NamedDependency[Settings], backends: NamedDependency[tuple[Backend, ...]]) -> ModelList:
    fleet = ", ".join(f"{backend.id}:{backend.model or backend.kind}" for backend in backends)
    names = (*settings.JEV_ALIASES, *(backend.model or backend.id for backend in backends))
    return ModelList(
        models=tuple(
            ModelMetadata(
                name=name, description=f"e-jev: System One over the fleet [{fleet}] — routing per question shape.", release_date=RELEASED
            )
            for name in dict.fromkeys(names)
        )
    )


ROUTES: Final[tuple[HTTPRouteHandler, ...]] = (
    post("/v1/systemone", name="systemone.evaluate", guards=[bearer], status_code=200)(evaluate),
    ### some open clients (pg-jev) join their base URL without the version prefix: same handler, bare path.
    post("/systemone", name="systemone.evaluate_bare", guards=[bearer], status_code=200)(evaluate),
    get("/v1/models", name="systemone.models", guards=[bearer])(models),
    get("/models", name="systemone.models_bare", guards=[bearer])(models),
)
