"""Build the configured model provider from the settings."""

from ticket_agent.llm.gemini import GeminiProvider
from ticket_agent.llm.provider import ModelProvider
from ticket_agent.settings import Settings


class ModelNotConfigured(Exception):
    """No API key is set, so no provider can be built; the message names the variable."""


def build_model_provider(settings: Settings) -> ModelProvider:
    """Create the Gemini provider for the key and model id in `settings`.

    Args:
        settings: process settings.

    Returns:
        A ready provider.

    Raises:
        ModelNotConfigured: `GEMINI_API_KEY` is unset; see the README for how to get one.
    """
    is_key_set = settings.gemini_api_key is not None

    if not is_key_set:
        raise ModelNotConfigured(
            "GEMINI_API_KEY is not set; put it in .env as described in the README"
        )

    api_key = settings.gemini_api_key.get_secret_value()
    provider = GeminiProvider(api_key=api_key, model_id=settings.gemini_model_id)

    return provider
