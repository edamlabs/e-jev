"""infra/config/cli: where `ejev` and `ejev-mcp` send their questions unless a flag says otherwise."""

from e_jev.infra.config.base import BaseSettings


##### SETTINGS #####
class CliSettings(BaseSettings):
    ### any System One endpoint: this e-jev, or TypeSafe's https://api.typesafe.ai with a real key.
    JEV_CLI_URL: str = "http://localhost:45160"
    JEV_CLI_KEY: str = "local"
    JEV_CLI_MODEL: str = "jev-latest"
