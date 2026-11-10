"""cli/commands/pull: every selected backend with weights is fetched into its own folder; the rest are named and skipped."""

from pathlib import Path

import pytest
from rich.console import Console

from e_jev.cli.commands import pull as command
from e_jev.infra.settings import Settings
from e_jev.models.catalog import HUB, BackendName


async def test_pull_fetches_only_what_has_weights(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[tuple[str, Path]] = []

    async def fake(repo: str, revision: str, folder: Path, **_: object) -> Path:
        fetched.append((f"{repo}@{revision}", folder))
        return folder

    monkeypatch.setattr(command, "hub_pull", fake)
    chosen = settings.model_copy(update={"JEV_BACKENDS": (BackendName.H2O_LIGHTNING_4B, BackendName.READING), "JEV_MODELS_DIR": tmp_path})
    console = Console(record=True, width=200)
    await command.pull(settings=chosen, console=console)
    spec = HUB[BackendName.H2O_LIGHTNING_4B]
    assert fetched == [(f"{spec.repo}@{spec.revision}", tmp_path / "h2o-lightning-4b")]
    assert "reading: no weights" in console.export_text()


async def test_pull_named_overrides_the_selection(settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[Path] = []

    async def fake(repo: str, revision: str, folder: Path, **_: object) -> Path:
        fetched.append(folder)
        return folder

    monkeypatch.setattr(command, "hub_pull", fake)
    await command.pull(
        BackendName.CLEF_FLASH, settings=settings.model_copy(update={"JEV_MODELS_DIR": tmp_path}), console=Console(quiet=True)
    )
    assert fetched == [tmp_path / "clef-flash"]
