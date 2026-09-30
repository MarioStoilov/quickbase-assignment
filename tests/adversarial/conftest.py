"""Fixtures of the live adversarial run: the real model, a fresh database, the report.

The tests here are marked `live_model` and deselected by the default `addopts`, so
`make test` never reaches the network. When selected, they skip without a key. The
application is built with the settings read from the environment and `.env`, minus
the database path, which points at a fresh temporary file seeded like production.
"""

import inspect
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from tests.constants.fixtures import TEST_BASE_URL, TEST_DATABASE_FILE_NAME
from tests.constants.live import LIVE_MODEL_MARKER, NO_KEY_SKIP_REASON
from tests.helpers.live import LiveReport, ScenarioRecord
from ticket_agent.app import create_app
from ticket_agent.cli import seed_database
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.schema import create_schema
from ticket_agent.settings import Settings, load_settings


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test in this package as a live-model test.

    Args:
        items: the collected tests.
    """
    package_directory = Path(__file__).parent
    for item in items:
        is_live_test = Path(str(item.fspath)).is_relative_to(package_directory)
        if is_live_test:
            item.add_marker(getattr(pytest.mark, LIVE_MODEL_MARKER))


@pytest.fixture(scope="session")
def live_report() -> Iterator[LiveReport]:
    """The report of this run, written to disk once every scenario has finished."""
    settings = load_settings()
    report = LiveReport(model_id=settings.gemini_model_id)

    yield report

    has_scenarios = len(report.scenarios) > 0
    if has_scenarios:
        report_path = report.write()
        print(f"\nlive adversarial report written to {report_path}")


@pytest.fixture
def live_settings(tmp_path: Path) -> Settings:
    """The environment's settings over a fresh temporary database; skips without a key."""
    environment_settings = load_settings()
    has_key = environment_settings.gemini_api_key is not None
    if not has_key:
        pytest.skip(NO_KEY_SKIP_REASON)

    database_path = tmp_path / TEST_DATABASE_FILE_NAME
    settings = environment_settings.model_copy(update={"database_path": database_path})

    return settings


@pytest.fixture
def live_app(live_settings: Settings) -> FastAPI:
    """The application over a seeded temporary database with the real model provider."""
    engine = create_database_engine(live_settings)
    create_schema(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as seed_session:
        seed_database(seed_session)
    engine.dispose()

    application = create_app(settings=live_settings)

    return application


@pytest.fixture
async def live_client(live_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client over the started application, real provider included."""
    async with live_app.router.lifespan_context(live_app):
        transport = httpx.ASGITransport(app=live_app)
        async with httpx.AsyncClient(transport=transport, base_url=TEST_BASE_URL) as client:
            yield client


@pytest.fixture
def scenario(request: pytest.FixtureRequest, live_report: LiveReport) -> ScenarioRecord:
    """The record of the current scenario, named after the test and its docstring."""
    description = inspect.cleandoc(request.function.__doc__ or "")
    record = live_report.new_scenario(request.node.name, description)

    return record


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> Iterator[None]:
    """Copy each live test's outcome into its scenario record for the report.

    Args:
        item: the test that ran.
        call: the phase that just finished.
    """
    outcome = yield
    report: pytest.TestReport = outcome.get_result()
    is_call_phase = report.when == "call"
    if not is_call_phase:
        return

    live_report = item.funcargs.get("live_report")
    has_report = live_report is not None
    if not has_report:
        return

    failure_text = report.longreprtext if report.failed else ""
    live_report.record_outcome(item.name, report.outcome, failure_text)
