"""cli/commands/pull: the weights of every selected backend that has them, into JEV_MODELS_DIR — the compose `models` step.

Each catalog entry with a Hub snapshot lands in `JEV_MODELS_DIR/<name>`, pinned and verified; one without weights
(`reading`, `systemone`: the endpoint is the deployment's) is skipped by name. Idempotent: a complete snapshot costs
one metadata round-trip, so every `docker compose up` may run it."""

import asyncio

from rich.console import Console

from e_jev.cli.runtime.deps import Inject
from e_jev.infra.settings import Settings
from e_jev.models.catalog import HUB, BackendName
from e_jev.ops.hub import hub_pull


async def pull(*names: BackendName, settings: Inject[Settings], console: Inject[Console]) -> None:
    """Fetch the weights of the named backends, or of JEV_BACKENDS when none is named.

    Args:
        names: catalog names; JEV_BACKENDS when empty.
    """
    wanted = tuple(dict.fromkeys(names or settings.JEV_BACKENDS))
    async with asyncio.TaskGroup() as group:
        tasks = {
            name: group.create_task(
                hub_pull(spec.repo, spec.revision, settings.JEV_MODELS_DIR / name, include=spec.include, exclude=spec.exclude)
            )
            for name in wanted
            if (spec := HUB.get(name))
        }
    console.print(
        "\n".join(
            f"[green]✓[/] {name} → {tasks[name].result()}"
            if name in tasks
            else f"[dim]· {name}: no weights, its endpoint is the deployment's[/]"
            for name in wanted
        )
    )
