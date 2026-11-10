"""logic/readout/prompts: a System One question as a lettered readout. Pure, no I/O.

Question -> lettered options in one prompt; the state leads, byte-identical across questions, so every question after
the first reuses its prefill."""

from dataclasses import dataclass
from typing import Final

from e_jev.logic.readout.labels import LETTERS, select_labels
from e_jev.models.systemone import Choice, Json, Noul, Question, Score, render_json

NOUL: Final = ("Yes", "No")
ASK: Final = "State:\n{state}\n\n{task} Reply with only the {unit} of your answer.\n\nQuestion:\n{instructions}\n\nOptions:\n{options}"


@dataclass(frozen=True, slots=True)
class Readout:
    task: str
    instructions: str
    options: tuple[str, ...]


def describe_option(name: str, description: Json | None) -> str:
    return f"{name} — {render_json(description)}" if description else name


def read_question(question: Question) -> Readout:
    match question:
        case Noul(instructions=instructions, criteria=criteria):
            meaning = (criteria.true, criteria.false) if criteria else (None, None)
            return Readout(
                task="Is the statement or question true of the state?",
                instructions=render_json(instructions),
                options=tuple(describe_option(name, text) for name, text in zip(NOUL, meaning, strict=True)),
            )
        case Choice(instructions=instructions, criteria=criteria):
            return Readout(
                task="Pick the option that best fits the state.",
                instructions=render_json(instructions),
                options=tuple(describe_option(name, text) for name, text in criteria.items()),
            )
        case Score(instructions=instructions, criteria=criteria):
            return Readout(
                task="Rate the state on this ordered scale, lowest level first.",
                instructions=render_json(instructions),
                options=tuple(render_json(level) for level in criteria),
            )


def prompt_readout(state: str, readout: Readout, order: tuple[int, ...]) -> str:
    """The prompt for one option order: labels follow the order, the options are permuted."""
    labels = select_labels(len(order))
    options = "\n".join(f"{label}. {readout.options[index]}" for label, index in zip(labels, order, strict=True))
    unit = "letter" if labels[0] == LETTERS[0] else "number"
    return ASK.format(task=readout.task, unit=unit, state=state, instructions=readout.instructions, options=options)


def orders_readout(size: int, permutations: int) -> tuple[tuple[int, ...], ...]:
    """Option orders to ask: identity, then reversed — each position bias meets its mirror."""
    identity = tuple(range(size))
    return (identity, identity[::-1])[:permutations]
