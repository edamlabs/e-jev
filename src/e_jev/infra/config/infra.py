"""infra/config/infra: the process — its environment and how loud it logs. e-jev's own: common's carries crypto it never signs with."""

from enum import StrEnum
from typing import Literal

from e_jev.infra.config.base import BaseSettings


##### ENUMS #####
class Env(StrEnum):
    PROD = "prod"
    DEV = "dev"
    LOCAL = "local"


##### SETTINGS #####
class InfraSettings(BaseSettings):
    """JEV_ENV picks the renderer (prod: JSON lines; dev, local: flat text), JEV_LOG_LEVEL the floor."""

    ### PROCESS
    JEV_ENV: Env = Env.PROD
    JEV_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
