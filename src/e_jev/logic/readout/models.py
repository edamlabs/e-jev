"""logic/readout/models: one readout's raw scores, the prompts it encoded and its passes — interior, never on the wire."""

from dataclasses import dataclass

from e_jev.ports.readout import Scores


@dataclass(frozen=True, slots=True)
class Reading:
    scores: Scores
    prompts: tuple[tuple[int, ...], ...]
    calls: int
