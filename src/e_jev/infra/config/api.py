"""infra/config/api: the HTTP door — who may call it and which names it answers to."""

from pydantic import field_validator

from e_jev.infra.config.base import BaseSettings


##### SETTINGS #####
class ApiSettings(BaseSettings):
    ### bearer key clients must send, as with TypeSafe; unset accepts any key (the SDKs require a non-empty one).
    JEV_API_KEY: str | None = None
    ### names /v1/models advertises beside the fleet's; requests may name any, the routed backend answers.
    JEV_ALIASES: tuple[str, ...] = ("jev-latest",)

    @field_validator("JEV_API_KEY", mode="before")
    @classmethod
    def _absent_key(cls, raw: object) -> object:
        """An empty key is no key: `JEV_API_KEY=` must not demand `Bearer ` from every client."""
        return None if raw == "" else raw
