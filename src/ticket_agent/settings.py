"""Runtime configuration, read from the environment in this module only.

Every other module receives a `Settings` instance or a value taken from one; nothing else
reads `os.environ`. Variables carry the `TICKET_AGENT_` prefix and may also be placed in a
`.env` file in the working directory (see `.env.example`).
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from ticket_agent.constants.environment import ENVIRONMENT_FILE_NAME, ENVIRONMENT_PREFIX


class Settings(BaseSettings):
    """All configuration values of one process, validated once at startup."""

    model_config = SettingsConfigDict(
        env_prefix=ENVIRONMENT_PREFIX,
        env_file=ENVIRONMENT_FILE_NAME,
        extra="ignore",
    )

    # Path of the SQLite database file. Relative paths are resolved against the working
    # directory. The file is created by `make init`; the server refuses to start without
    # it. Default: `data/tickets.db`.
    database_path: Path = Path("data/tickets.db")

    # Interface the API server binds to. Default: loopback only.
    host: str = "127.0.0.1"

    # TCP port the API server listens on. Default: 8000.
    port: int = 8000

    @property
    def database_url(self) -> str:
        """SQLAlchemy URL for the configured SQLite file."""
        return f"sqlite:///{self.database_path}"


def load_settings() -> Settings:
    """Read the settings from the environment and the optional `.env` file.

    Returns:
        A validated `Settings` instance.

    Raises:
        pydantic.ValidationError: a variable is present but has the wrong type.
    """
    settings = Settings()

    return settings
