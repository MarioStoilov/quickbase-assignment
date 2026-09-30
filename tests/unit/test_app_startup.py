"""Startup refuses a missing schema and a missing key, and the provider factory."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from tests.fakes.scripted_provider import ScriptedProvider
from ticket_agent.app import DatabaseNotInitialised, create_app
from ticket_agent.constants.cli import INIT_COMMAND_HINT
from ticket_agent.constants.llm import DEFAULT_GEMINI_MODEL_ID
from ticket_agent.llm.factory import ModelNotConfigured, build_model_provider
from ticket_agent.llm.gemini import GeminiProvider
from ticket_agent.settings import Settings, load_settings


@pytest.mark.anyio
async def test_startup_without_schema_names_the_init_command(settings: Settings) -> None:
    """A database file without tables stops the server with a message naming make init."""
    application = create_app(settings=settings, model_provider=ScriptedProvider())

    with pytest.raises(DatabaseNotInitialised, match=INIT_COMMAND_HINT):
        async with application.router.lifespan_context(application):
            pass


@pytest.mark.anyio
async def test_startup_without_key_or_provider_names_the_variable(
    settings: Settings, engine: object
) -> None:
    """With a schema but no key and no injected provider, startup names GEMINI_API_KEY."""
    application = create_app(settings=settings)

    with pytest.raises(ModelNotConfigured, match="GEMINI_API_KEY"):
        async with application.router.lifespan_context(application):
            pass


def test_factory_builds_a_gemini_provider_from_a_key(tmp_path: Path) -> None:
    """A configured key yields the Gemini adapter for the configured model id."""
    configured = Settings(
        database_path=tmp_path / "x.db",
        gemini_api_key=SecretStr("not-a-real-key"),
        gemini_model_id="some-model",
    )

    provider = build_model_provider(configured)

    assert isinstance(provider, GeminiProvider)


def test_settings_read_the_environment_with_the_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prefixed variables set the fields; the key is read under its plain name."""
    monkeypatch.setenv("TICKET_AGENT_DATABASE_PATH", str(tmp_path / "env.db"))
    monkeypatch.setenv("TICKET_AGENT_PORT", "9001")
    monkeypatch.setenv("TICKET_AGENT_MAX_TOOL_ROUNDS", "3")
    monkeypatch.setenv("GEMINI_API_KEY", "plain-key")
    monkeypatch.delenv("TICKET_AGENT_GEMINI_MODEL_ID", raising=False)

    loaded = load_settings()

    assert loaded.database_path == tmp_path / "env.db"
    assert loaded.port == 9001
    assert loaded.max_tool_rounds == 3
    assert loaded.gemini_api_key.get_secret_value() == "plain-key"
    assert loaded.gemini_model_id == DEFAULT_GEMINI_MODEL_ID
    assert loaded.database_url.endswith("env.db")


@pytest.mark.anyio
async def test_shutdown_closes_the_provider(settings: Settings, engine: object) -> None:
    """Leaving the lifespan closes the provider so its connections do not outlive the loop."""
    provider = ScriptedProvider()
    application = create_app(settings=settings, model_provider=provider)

    async with application.router.lifespan_context(application):
        assert provider.is_closed is False

    assert provider.is_closed is True
