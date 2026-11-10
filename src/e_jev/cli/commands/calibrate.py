"""cli/commands/calibrate: fit one temperature per (backend, kind) on labeled JSONL, through that backend itself.

Runs where the fleet's settings live. The backend answers over the same Decider the service will use — the
reading one still reads vLLM's raw logprobs, a native one answers with its published probabilities — so a
fit always describes what routing will see. Each example falls in a stable half, fit or held out, and every
number reported (ECE before and after, accuracy per source) comes from the held-out half. The result is
merged into the calibration file under its backend id; other backends' fits are kept. Refit whenever a
backend changes or JEV_PERMUTATIONS moves; the service applies only what was fitted under this permutation
count. One labeled System One question per line:
    {"state": "...", "question": {"type": "choice", "instructions": "...", "criteria": {"a": null}}, "label": "a", "source": "x"}
"""

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path

import msgspec
from rich.console import Console
from rich.table import Table

from e_jev.api.lifespan.engines import openers, resolve
from e_jev.cli.runtime.deps import Inject
from e_jev.cli.views import HEADER
from e_jev.infra.settings import Settings
from e_jev.logic.calibration.fit import Scored, fit_kinds, split_held
from e_jev.logic.decision.answers import index_label
from e_jev.models.calibration import Calibration, KindFit, Labeled
from e_jev.models.error import CliError
from e_jev.models.systemone import QuestionKind, render_json


class BackendError(CliError):
    """The fleet has no such backend, or it will not answer."""

    exit_code = 3


async def calibrate(
    file: Path,
    *,
    backend: str = "reading",
    settings: Inject[Settings],
    console: Inject[Console],
) -> None:
    """Fit per-kind temperatures for one backend on half the examples, measure on the other, merge into the file.

    Args:
        file: JSONL, one labeled System One question per line.
        backend: catalog name to fit, one of JEV_BACKENDS.
    """
    samples = tuple(msgspec.json.Decoder(Labeled).decode_lines(await asyncio.to_thread(file.read_bytes)))
    backends = resolve(settings)
    match next((item for item in backends if item.id == backend), None):
        case None:
            message = f"backend {backend!r} is not in JEV_BACKENDS: {[item.id for item in backends]}"
            raise BackendError(message)
        case wanted:
            async with AsyncExitStack() as stack:
                decider = await openers((wanted,), settings)[wanted.id](stack)
                slots = asyncio.Semaphore(wanted.concurrency)

                async def one(sample: Labeled) -> tuple[Labeled, Scored]:
                    async with slots:
                        decision = await decider.decide(render_json(sample.state), {"q": sample.question})
                    return sample, Scored(
                        kind=QuestionKind.of(sample.question),
                        source=sample.source,
                        scores=decision.scores["q"],
                        label=index_label(sample.question, sample.label),
                        held=split_held(msgspec.json.encode([sample.state, sample.question])),
                    )

                async with asyncio.TaskGroup() as group:
                    tasks = [group.create_task(one(sample)) for sample in samples]
    answered = [task.result() for task in tasks]
    rows = [scored for _, scored in answered]
    fit = fit_kinds(rows)
    entry = KindFit(
        model=wanted.model or wanted.id,
        temperatures={QuestionKind(kind): value for kind, value in fit.temperatures.items()},
        ece_before={QuestionKind(kind): value for kind, value in fit.ece_before.items()},
        ece_after={QuestionKind(kind): value for kind, value in fit.ece_after.items()},
        accuracy=fit.accuracy,
        fitted=sum(not row.held for row in rows),
        held_out=sum(row.held for row in rows),
    )
    stored = Calibration.load(settings.JEV_CALIBRATION, settings.JEV_PERMUTATIONS)
    merged = Calibration(
        permutations=settings.JEV_PERMUTATIONS,
        backends=(stored.backends if stored else {}) | {backend: entry},
    )
    await asyncio.to_thread(settings.JEV_CALIBRATION.write_bytes, msgspec.json.format(msgspec.json.encode(merged)))
    table = Table("kind", "temperature", "ECE before", "ECE after", box=None, header_style=HEADER)
    for kind, temperature in entry.temperatures.items():
        table.add_row(kind, f"{temperature:.3f}", f"{entry.ece_before[kind]:.3f}", f"{entry.ece_after[kind]:.3f}")
    console.print(table)
    console.print(", ".join(f"{source} {value:.1%}" for source, value in entry.accuracy.items()))
    console.print(f"[green]✓[/] {backend}: fitted on {entry.fitted}, measured on {entry.held_out} held out · {settings.JEV_CALIBRATION}")
