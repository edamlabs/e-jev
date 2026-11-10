"""infra/settings: the one `Settings` — every cluster of `infra/config`, read once, at import.

Only the composition roots (`main`, the CLI's runtime, the MCP server) import `settings` and hand each provider,
engine and runner its typed values; everything below takes plain keyword arguments."""

from e_jev.infra.config.api import ApiSettings
from e_jev.infra.config.cli import CliSettings
from e_jev.infra.config.infra import InfraSettings
from e_jev.infra.config.logic import LogicSettings
from e_jev.infra.config.providers import ProviderSettings


##### SETTINGS #####
class Settings(InfraSettings, ProviderSettings, LogicSettings, ApiSettings, CliSettings):
    """Every cluster, one contract."""


settings = Settings()
