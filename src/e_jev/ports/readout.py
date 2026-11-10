"""ports/readout: a generative LLM read at the token level — the chat template, next-token logprobs, schema-bound generation."""

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import numpy as np

from e_jev.models.systemone import Json
from e_jev.ports.provider import Provider

### spelled as ndarray[shape, dtype]: NumPy's NDArray is a TypeAliasType beartype cannot resolve; this form it checks.
type Scores = np.ndarray[tuple[int, ...], np.dtype[np.float64]]


##### PORT #####
@runtime_checkable
class ReadoutPort(Provider, Protocol):
    @property
    def model(self) -> str:
        """The served model the readouts come from: the name calibration fits are bound to."""
        ...

    @property
    def stop(self) -> int:
        """The token that closes an answer turn."""
        ...

    def label(self, text: str) -> tuple[int, ...]:
        """The token sequence of one option label, as the model writes it."""
        ...

    async def encode(self, prompt: str) -> tuple[int, ...]:
        """The prompt as a user turn, rendered by the chat template up to the start of the answer."""
        ...

    async def logprobs(self, tokens: Sequence[int], candidates: Sequence[int]) -> Scores:
        """Next-token log-probabilities after `tokens`, one per candidate, in candidate order."""
        ...

    async def extract(self, prompt: str, schema: dict[str, Any]) -> Json:
        """A value generated under `schema`."""
        ...
