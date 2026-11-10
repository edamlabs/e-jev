"""ports/sink: where every answered question is written for the distillation loop — state, question, raw scores, backend."""

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from e_jev.models.systemone import Question
from e_jev.ports.provider import Provider


##### PORT #####
@runtime_checkable
class SinkPort(Provider, Protocol):
    def record(self, state: str, question: Question, scores: Sequence[float], backend: str) -> None: ...
