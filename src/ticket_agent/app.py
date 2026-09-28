"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ticket_agent import APPLICATION_DESCRIPTION, APPLICATION_NAME, __version__
from ticket_agent.api import health, tenants, tickets
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.schema import schema_exists
from ticket_agent.settings import Settings, load_settings

# Command a reader is pointed at when the database has not been initialised.
INIT_COMMAND_HINT = "make init"


class DatabaseNotInitialised(Exception):
    """The configured database file lacks the schema; `make init` has not been run."""


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application with its routers and database wiring.

    The database schema is checked at startup, not at import time, so that building the
    application (for example to inspect its routes) needs no database.

    Args:
        settings: process settings; loaded from the environment when None.

    Returns:
        The configured FastAPI application.
    """
    is_settings_given = settings is not None
    if not is_settings_given:
        settings = load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Open the database at startup and dispose of it at shutdown.

        Raises:
            DatabaseNotInitialised: the schema is missing; the message names `make init`.
        """
        engine = create_database_engine(settings)
        is_initialised = schema_exists(engine)

        if not is_initialised:
            engine.dispose()
            raise DatabaseNotInitialised(
                f"database {settings.database_path} has no schema; run `{INIT_COMMAND_HINT}` first"
            )

        application.state.settings = settings
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)

        yield

        engine.dispose()

    application = FastAPI(
        title=APPLICATION_NAME,
        description=APPLICATION_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )
    application.include_router(health.router)
    application.include_router(tenants.router)
    application.include_router(tickets.router)

    return application
