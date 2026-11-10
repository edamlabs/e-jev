"""infra/config/providers: JEV_BACKENDS is catalog names — the plain comma form, JSON too, nothing outside the catalog."""

import pytest
from pydantic import ValidationError

from e_jev.infra.settings import Settings
from e_jev.models.catalog import BackendName


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("h2o-lightning-4b", (BackendName.H2O_LIGHTNING_4B,)),
        ("h2o-lightning-4b, reading", (BackendName.H2O_LIGHTNING_4B, BackendName.READING)),
        ('["clef-flash", "reading"]', (BackendName.CLEF_FLASH, BackendName.READING)),
    ],
    ids=["single", "comma", "json"],
)
def test_backends_parse(monkeypatch: pytest.MonkeyPatch, raw: str, expected: tuple[BackendName, ...]) -> None:
    monkeypatch.setenv("JEV_BACKENDS", raw)
    assert expected == Settings().JEV_BACKENDS


def test_backends_default_reading() -> None:
    assert Settings().JEV_BACKENDS == (BackendName.READING,)


def test_backends_unknown_lists_the_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_BACKENDS", "h2o")
    with pytest.raises(ValidationError, match="'reading', 'systemone', 'h2o-lightning-4b' or 'clef-flash'"):
        Settings()


@pytest.mark.parametrize("variable", ["JEV_DECISION_LOG", "JEV_OTLP_ENDPOINT", "JEV_READING_PRIORITY", "JEV_API_KEY"])
def test_empty_variable_is_absent(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    monkeypatch.setenv(variable, "")
    assert getattr(Settings(), variable) is None
