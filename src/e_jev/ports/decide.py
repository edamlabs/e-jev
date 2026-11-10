"""ports/decide: a state and its whole set of questions in, raw option scores out — one call per backend, whatever it is."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from e_jev.models.systemone import Question
from e_jev.ports.readout import Scores


##### TYPES #####
@dataclass(frozen=True, slots=True)
class Decision:
    """Per-question score vectors over the question's options, in order and in log space, as one backend produced them.

    Tokens are what the backend billed: the reading path counts them from its prompts, a native server answers with
    the usage its own API reports."""

    scores: Mapping[str, Scores]
    input_tokens: int
    output_tokens: int = 0


##### PORT #####
@runtime_checkable
class DecidePort(Protocol):
    """Request level: one backend of the fleet. Capacity and contract failures raise; `health` says whether it serves."""

    @property
    def backend(self) -> str:
        """The fleet id this backend answers as: the key its calibration is fitted under."""
        ...

    async def decide(self, state: str, questions: Mapping[str, Question]) -> Decision: ...

    async def health(self) -> bool: ...
