"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ticket_agent import __version__
from ticket_agent.api import chat, health, tenants, tickets
from ticket_agent.auth import TenantAuthMiddleware
from ticket_agent.constants.application import APPLICATION_DESCRIPTION, APPLICATION_NAME
from ticket_agent.constants.cli import INIT_COMMAND_HINT
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.schema import schema_exists
from ticket_agent.llm.factory import ModelNotConfigured, build_model_provider
from ticket_agent.llm.provider import ModelProvider
from ticket_agent.settings import Settings, load_settings


class DatabaseNotInitialised(Exception):
    """The configured database file lacks the schema; `make init` has not been run."""


def create_app(
    settings: Settings | None = None, model_provider: ModelProvider | None = None
) -> FastAPI:
    """Build the application with its routers, database wiring and model provider.

    The database schema and the model provider are checked at startup, not at import
    time, so that building the application (for example to inspect its routes) needs
    neither a database nor an API key.

    Args:
        settings: process settings; loaded from the environment when None.
        model_provider: the model to chat with; built from the settings when None. Tests
            pass a scripted one so no network or key is needed.

    Returns:
        The configured FastAPI application.
    """
    is_settings_given = settings is not None
    if not is_settings_given:
        settings = load_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Open the database and the model provider at startup; dispose at shutdown.

        Raises:
            DatabaseNotInitialised: the schema is missing; the message names `make init`.
            ModelNotConfigured: no provider was given and `GEMINI_API_KEY` is unset.
        """
        engine = create_database_engine(settings)
        is_initialised = schema_exists(engine)

        if not is_initialised:
            engine.dispose()
            raise DatabaseNotInitialised(
                f"database {settings.database_path} has no schema; run `{INIT_COMMAND_HINT}` first"
            )

        # The provider is built at startup rather than per request so that a missing
        # key stops the server, like a missing schema, instead of failing the first
        # chat. It comes after the schema check so one problem is reported at a time.
        is_provider_given = model_provider is not None
        provider = model_provider
        if not is_provider_given:
            try:
                provider = build_model_provider(settings)
            except ModelNotConfigured:
                engine.dispose()
                raise

        application.state.settings = settings
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.model_provider = provider

        yield

        engine.dispose()

    application = FastAPI(
        title=APPLICATION_NAME,
        description=APPLICATION_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(TenantAuthMiddleware)
    application.include_router(health.router)
    application.include_router(tenants.router)
    application.include_router(tickets.router)
    application.include_router(chat.router)

    return application
