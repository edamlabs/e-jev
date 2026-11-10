"""logic/decision/answers: a calibrated distribution over a question's options, as TypeSafe's typed answer. Pure, no I/O.

Confidence follows TypeSafe's reference definitions (typesafe-ai/system-one-adapter-python): choice rescales the peak
from uniform to certainty; score is 1 minus the mean distance from the mode, relative to that of a uniform distribution."""

import numpy as np

from e_jev.models.error import LabelIndexError
from e_jev.models.systemone import Answer, Choice, ChoiceAnswer, Noul, NoulAnswer, Question, Score, ScoreAnswer
from e_jev.ports.readout import Scores


def confidence_choice(probs: Scores) -> float:
    uniform = 1 / probs.size
    return float((probs.max() - uniform) / (1 - uniform))


def confidence_score(probs: Scores) -> float:
    levels = np.arange(probs.size)
    spread = np.abs(levels - (probs.size - 1) / 2).mean()
    return float(max(0.0, 1 - (probs * np.abs(levels - probs.argmax())).sum() / spread))


def build_answer(question: Question, probs: Scores) -> Answer:
    match question:
        case Noul():
            return NoulAnswer(noul=float(probs[0]))
        case Choice(criteria=criteria):
            return ChoiceAnswer(
                choice=tuple(criteria)[int(probs.argmax())],
                probabilities=dict(zip(criteria, probs.tolist(), strict=True)),
                confidence=confidence_choice(probs),
            )
        case Score(criteria=criteria):
            return ScoreAnswer(
                score=float((np.arange(probs.size) * probs).sum()),
                legend={str(level): text for level, text in enumerate(criteria)},
                probabilities={str(level): p for level, p in enumerate(probs.tolist())},
                confidence=confidence_score(probs),
            )


def index_label(question: Question, label: str) -> int:
    """Position of a calibration label among the question's options."""
    keys: tuple[str, ...]
    match question:
        case Noul():
            keys, key = ("true", "false"), label.lower()
        case Choice(criteria=criteria):
            keys, key = tuple(criteria), label
        case Score(criteria=criteria):
            keys, key = tuple(map(str, range(len(criteria)))), label
    match key:
        case found if found in keys:
            return keys.index(found)
        case _:
            raise LabelIndexError(label, keys)
