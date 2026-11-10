"""models/catalog: the decision backends e-jev knows by name — how each is reached, what it may answer, where its weights live.

`JEV_BACKENDS` names entries of this bank and nothing else: a name outside it fails the settings load with the list
of valid ones. An entry is a template; the composition root fills what the deployment decides (the URL, the key, the
served model) from the settings. A backend with weights carries its pinned Hub snapshot: `ejev pull` fetches it into
`JEV_MODELS_DIR/<name>`, where its server container reads it."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum, auto
from types import MappingProxyType
from typing import Final


##### TYPES #####
class BackendKind(StrEnum):
    """How a backend is reached: the logprob reader over an LLM endpoint, or a native `/v1/systemone` server."""

    READING = auto()
    SYSTEMONE = auto()


class BackendName(StrEnum):
    """The catalog: every value `JEV_BACKENDS` accepts."""

    READING = "reading"
    SYSTEMONE = "systemone"
    H2O_LIGHTNING_4B = "h2o-lightning-4b"
    CLEF_FLASH = "clef-flash"


class Language(StrEnum):
    """The language axis a state is routed by: the only one the contract must know, Spanish first."""

    ANY = auto()
    EN = auto()
    ES = auto()


@dataclass(frozen=True, slots=True)
class Backend:
    """One routable backend: its id is the fleet key and the key its calibration is fitted under."""

    id: str
    kind: BackendKind
    url: str = ""
    api_key: str = "local"
    ### served model name, sent in every request and bound to every calibration fit.
    model: str = ""
    languages: tuple[Language, ...] = (Language.ANY,)
    max_options: int = 255
    max_state_tokens: int = 32_768
    concurrency: int = 16
    timeout: float = 120.0
    description: str = ""


@dataclass(frozen=True, slots=True)
class HubSpec:
    """One pinned Hub snapshot: the repo, its revision (a tag or a commit), the files worth fetching (every file when empty)."""

    repo: str
    revision: str
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


##### BANK #####
CATALOG: Final[Mapping[BackendName, Backend]] = MappingProxyType(
    {
        BackendName.READING: Backend(
            id=BackendName.READING,
            kind=BackendKind.READING,
            concurrency=8,
            description="option-letter logprobs read from any OpenAI-compatible LLM speaking vLLM's dialect "
            "(/tokenize + /v1/completions with logprob_token_ids): JEV_READING_URL and JEV_READING_MODEL required",
        ),
        BackendName.SYSTEMONE: Backend(
            id=BackendName.SYSTEMONE,
            kind=BackendKind.SYSTEMONE,
            description="any native /v1/systemone server (TypeSafe's Jev, Laya, Kev…): JEV_SYSTEMONE_URL required",
        ),
        BackendName.H2O_LIGHTNING_4B: Backend(
            id=BackendName.H2O_LIGHTNING_4B,
            kind=BackendKind.SYSTEMONE,
            url="http://h2o:8741",
            model="h2oai/h2o-lightning-4b",
            description="H2O-Lightning-4B v1.4.2 (Apache-2.0): vLLM 0.30 + H2O's shim, two-way attention, 32k state",
        ),
        BackendName.CLEF_FLASH: Backend(
            id=BackendName.CLEF_FLASH,
            kind=BackendKind.SYSTEMONE,
            url="http://clef:8080",
            model="clef",
            max_state_tokens=4096,
            description="Clef-Flash Q4_K_M (Apache-2.0) on llama.cpp: joint decision head, states up to ~4k tokens",
        ),
    }
)

HUB: Final[Mapping[BackendName, HubSpec]] = MappingProxyType(
    {
        BackendName.H2O_LIGHTNING_4B: HubSpec(
            repo="h2oai/h2o-lightning-4b", revision="839c5c9523764f0b68c2785944f5541ee66a92b8", exclude=("assets/*",)
        ),
        BackendName.CLEF_FLASH: HubSpec(
            repo="ggml-org/Clef-Flash-GGUF", revision="a5a18a6e13bb36573a5f11385a1e7b9a0c868e9e", include=("Clef-Flash-Q4_K_M.gguf",)
        ),
    }
)
