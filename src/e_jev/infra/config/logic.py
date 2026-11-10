"""infra/config/logic: how decisions are read, calibrated and recorded."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator

from e_jev.infra.config.base import BaseSettings


##### SETTINGS #####
class LogicSettings(BaseSettings):
    ### READOUT
    ### 2 asks every question in both option orders and averages: removes position bias at ~2x cost (reading only).
    JEV_PERMUTATIONS: Annotated[int, Field(ge=1, le=2)] = 1
    ### probability mass a multi-token choice may leave unread (uniform instead): its TV-distance bound. 0 reads all.
    JEV_TRIE_EPSILON: Annotated[float, Field(ge=0, le=0.01)] = 1e-4

    ### CALIBRATION — one temperature per (backend, kind), fitted with `ejev calibrate`
    JEV_CALIBRATION: Path = Path("/data/calibration.json")

    ### DISTILLATION — JSONL of every answered question; unset logs nothing
    JEV_DECISION_LOG: Path | None = None

    @field_validator("JEV_DECISION_LOG", mode="before")
    @classmethod
    def _absent_log(cls, raw: object) -> object:
        """An empty variable is an unset one — compose writes `VAR=` for a default it leaves blank; never Path(".")."""
        return None if raw == "" else raw
