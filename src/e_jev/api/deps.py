"""api/deps: request-scoped wiring — handlers receive typed branches, never the raw app state."""

from enum import StrEnum
from typing import Final

from litestar.datastructures import State
from litestar.di import Provide

from e_jev.infra.settings import Settings
from e_jev.logic.decision.runner import DecisionRunner
from e_jev.models.catalog import Backend


class DepKey(StrEnum):
    RUNNER = "runner"
    BACKENDS = "backends"
    SETTINGS = "settings"


def provide_runner(state: State) -> DecisionRunner:
    return state.runner


def provide_backends(state: State) -> tuple[Backend, ...]:
    return state.backends


def provide_settings(state: State) -> Settings:
    return state.settings


DEPENDENCIES: Final[dict[str, Provide]] = {
    DepKey.RUNNER.value: Provide(provide_runner, sync_to_thread=False),
    DepKey.BACKENDS.value: Provide(provide_backends, sync_to_thread=False),
    DepKey.SETTINGS.value: Provide(provide_settings, sync_to_thread=False),
}
