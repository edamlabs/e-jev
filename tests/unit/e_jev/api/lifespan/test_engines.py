"""api/lifespan/engines: catalog names become backends with the deployment's endpoints — or the start refuses, naming the variable."""

import pytest

from e_jev.api.lifespan.engines import openers, resolve
from e_jev.infra.settings import Settings
from e_jev.models.catalog import BackendKind, BackendName
from e_jev.models.error import MissingEndpointError


def test_resolve_fills_the_deployment(settings: Settings) -> None:
    chosen = settings.model_copy(
        update={"JEV_BACKENDS": (BackendName.H2O_LIGHTNING_4B, BackendName.READING), "JEV_H2O_URL": "http://gpu:8741"}
    )
    h2o, reading = resolve(chosen)
    assert (h2o.id, h2o.kind, h2o.url, h2o.model) == (
        "h2o-lightning-4b",
        BackendKind.SYSTEMONE,
        "http://gpu:8741",
        "h2oai/h2o-lightning-4b",
    )
    assert (reading.url, reading.model, reading.max_state_tokens) == ("http://reading/v1", "m", 32_768)


def test_resolve_keeps_the_first_mention(settings: Settings) -> None:
    twice = settings.model_copy(update={"JEV_BACKENDS": (BackendName.CLEF_FLASH, BackendName.CLEF_FLASH)})
    assert [backend.id for backend in resolve(twice)] == ["clef-flash"]


@pytest.mark.parametrize(
    ("name", "unset", "named"),
    [
        (BackendName.READING, {"JEV_READING_URL": ""}, "JEV_READING_URL"),
        (BackendName.READING, {"JEV_READING_MODEL": ""}, "JEV_READING_MODEL"),
        (BackendName.SYSTEMONE, {}, "JEV_SYSTEMONE_URL"),
    ],
)
def test_resolve_refuses_an_unset_endpoint(settings: Settings, name: BackendName, unset: dict[str, str], named: str) -> None:
    with pytest.raises(MissingEndpointError, match=named):
        resolve(settings.model_copy(update={"JEV_BACKENDS": (name,), **unset}))


def test_openers_one_per_backend(settings: Settings) -> None:
    chosen = settings.model_copy(update={"JEV_BACKENDS": (BackendName.READING, BackendName.CLEF_FLASH)})
    assert list(openers(resolve(chosen), chosen)) == ["reading", "clef-flash"]
