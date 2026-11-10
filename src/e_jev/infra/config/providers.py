"""infra/config/providers: which catalog backends make the fleet, and where each one, its weights and its traces live."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import NoDecode

from e_jev.infra.config.base import BaseSettings
from e_jev.models.catalog import BackendName
from e_jev.models.systemone import QuestionKind


##### SETTINGS #####
class ProviderSettings(BaseSettings):
    """JEV_BACKENDS is the whole choice: catalog names, comma-separated, preferred first — `reading` by default.
    A name outside the catalog fails the load and lists the valid ones; the service refuses to start on a selected
    backend whose endpoint is unset (the CLI and `ejev pull` load these settings too, and need no endpoint)."""

    ### FLEET
    JEV_BACKENDS: Annotated[tuple[BackendName, ...], NoDecode] = (BackendName.READING,)
    ### per question kind, a preference row of selected names (JSON); a question falls down its row on failure.
    JEV_ROWS: dict[QuestionKind, tuple[BackendName, ...]] = Field(default_factory=dict)

    ### READING — any OpenAI-compatible LLM speaking vLLM's logprob dialect; also the extractor
    JEV_READING_URL: str = ""
    JEV_READING_KEY: str = "local"
    JEV_READING_MODEL: str = ""
    ### vLLM `--scheduling-policy priority` only: higher waits longer — e-jev as bulk load behind interactive clients.
    JEV_READING_PRIORITY: int | None = None
    JEV_READING_MAX_STATE_TOKENS: Annotated[int, Field(ge=64)] = 32_768
    JEV_EXTRACT_MAX_TOKENS: Annotated[int, Field(ge=1)] = 1024

    ### SYSTEMONE — any native /v1/systemone server
    JEV_SYSTEMONE_URL: str = ""
    JEV_SYSTEMONE_KEY: str = "local"
    JEV_SYSTEMONE_MODEL: str = ""

    ### CATALOG SERVERS — the compose service names by default
    JEV_H2O_URL: str = "http://h2o:8741"
    JEV_CLEF_URL: str = "http://clef:8080"

    ### HUB — where `ejev pull` writes each backend's weights, one folder per catalog name
    JEV_MODELS_DIR: Path = Path("/models")

    ### TELEMETRY — OTLP/HTTP traces endpoint (Phoenix: http://phoenix:6006/v1/traces); unset keeps tracing off
    JEV_OTLP_ENDPOINT: str | None = None
    JEV_OTLP_PROJECT: str = "e-jev"

    @field_validator("JEV_READING_PRIORITY", "JEV_OTLP_ENDPOINT", mode="before")
    @classmethod
    def _absent_endpoint(cls, raw: object) -> object:
        """An empty variable is an unset one — compose writes `VAR=` for a default it leaves blank."""
        return None if raw == "" else raw

    @field_validator("JEV_BACKENDS", mode="before")
    @classmethod
    def _split(cls, raw: object) -> object:
        """`h2o-lightning-4b,reading` — the plain form an installer types; a JSON list stays accepted."""
        match raw:
            case str() as text if text.strip().startswith("["):
                return tuple(name.strip(' "') for name in text.strip("[] ").split(",") if name.strip(' "'))
            case str() as text:
                return tuple(name.strip() for name in text.split(",") if name.strip())
            case _:
                return raw
