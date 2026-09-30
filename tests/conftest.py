"""Fixtures shared by every test layer.

Each test gets its own SQLite file under pytest's temporary directory, created through
the same schema and seed code `make init` runs, so the data a test sees is exactly the
seed data. The application is built through `create_app` with a scripted provider, so
no test needs a network connection or an API key.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from tests.fakes.scripted_provider import ScriptedProvider
from ticket_agent.app import create_app
from ticket_agent.cli import seed_database
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.schema import create_schema
from ticket_agent.settings import Settings

# Name of the per-test database file inside pytest's temporary directory.
TEST_DATABASE_FILE_NAME = "tickets-test.db"

# Base URL the ASGI transport answers under; never dialled.
TEST_BASE_URL = "http://testserver"


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only, the loop uvicorn uses."""
    return "asyncio"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a fresh database file, with no API key.

    Args:
        tmp_path: pytest's per-test directory.

    Returns:
        Settings the tests and the application share.
    """
    database_path = tmp_path / TEST_DATABASE_FILE_NAME
    test_settings = Settings(database_path=database_path, gemini_api_key=None)

    return test_settings


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    """An engine on the test database with the schema created and the seed data loaded.

    Args:
        settings: the per-test settings.

    Yields:
        The engine; disposed afterwards.
    """
    test_engine = create_database_engine(settings)
    create_schema(test_engine)

    session_factory = create_session_factory(test_engine)
    with session_factory() as seed_session:
        seed_database(seed_session)

    yield test_engine

    test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session on the seeded test database.

    Args:
        engine: the seeded engine.

    Yields:
        The session; closed afterwards.
    """
    session_factory = create_session_factory(engine)
    test_session = session_factory()

    yield test_session

    test_session.close()


@pytest.fixture
def scripted_provider() -> ScriptedProvider:
    """The fake model the application is built with; tests script its turns."""
    provider = ScriptedProvider()

    return provider


@pytest.fixture
def app(settings: Settings, engine: Engine, scripted_provider: ScriptedProvider) -> FastAPI:
    """The application over the seeded database with the scripted provider.

    Args:
        settings: the per-test settings.
        engine: the seeded engine; requested so the schema exists before startup.
        scripted_provider: the fake model.

    Returns:
        The FastAPI application, not yet started.
    """
    application = create_app(settings=settings, model_provider=scripted_provider)

    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client driving the started application in-process.

    The lifespan is entered by hand because httpx's ASGI transport does not run it, and
    startup is where the engine, session factory, provider and registry are attached.

    Args:
        app: the application.

    Yields:
        The client; the lifespan exits afterwards.
    """
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as test_client:
            yield test_client
