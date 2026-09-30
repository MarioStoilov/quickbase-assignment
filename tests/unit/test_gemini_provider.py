"""`GeminiProvider` with a fake SDK client: retries, errors and the event stream."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import pytest
from google.genai import errors, types

from tests.constants.provider import FAKE_API_KEY, FAKE_MODEL_ID
from ticket_agent.constants.llm import (
    FINISH_REASON_STOP,
    FINISH_REASON_TOOL_CALLS,
    MODEL_REQUEST_ATTEMPTS,
    THOUGHT_SIGNATURE_KEY,
)
from ticket_agent.llm.conversation import UserMessage
from ticket_agent.llm.events import TextDelta, ToolCallRequest, TurnFinished
from ticket_agent.llm.gemini import provider as provider_module
from ticket_agent.llm.gemini.provider import GeminiProvider
from ticket_agent.llm.provider import ModelProviderError


def transient_error() -> errors.APIError:
    """Build the quota error the SDK raises when the free tier's window is hit."""
    api_error = errors.APIError(
        429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )

    return api_error


def permanent_error() -> errors.APIError:
    """Build an error that must not be retried."""
    api_error = errors.APIError(
        400, {"error": {"message": "bad request", "status": "INVALID_ARGUMENT"}}
    )

    return api_error


async def chunks(
    *streamed_chunks: types.GenerateContentResponse,
) -> AsyncIterator[types.GenerateContentResponse]:
    """Yield the given chunks as the SDK's stream would.

    Args:
        streamed_chunks: the chunks in order.

    Yields:
        Each chunk.
    """
    for streamed_chunk in streamed_chunks:
        yield streamed_chunk


@dataclass
class FakeModels:
    """Stands in for `client.aio.models`: raises the queued errors, then streams."""

    errors_to_raise: list[errors.APIError] = field(default_factory=list)
    stream_chunks: list[types.GenerateContentResponse] = field(default_factory=list)
    requested_model_ids: list[str] = field(default_factory=list)

    async def generate_content_stream(
        self, model: str, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """Record the call, raise the next queued error, or return the stream."""
        self.requested_model_ids.append(model)
        has_error = len(self.errors_to_raise) > 0
        if has_error:
            raise self.errors_to_raise.pop(0)

        return chunks(*self.stream_chunks)


@dataclass
class FakeAio:
    """The `aio` namespace of the fake client."""

    models: FakeModels
    is_closed: bool = False

    async def aclose(self) -> None:
        """Record that the provider closed the client."""
        self.is_closed = True


@dataclass
class FakeClient:
    """The fake SDK client: only what the provider touches."""

    aio: FakeAio


def provider_with(fake_models: FakeModels) -> GeminiProvider:
    """Build a provider and swap its SDK client for the fake.

    Args:
        fake_models: the fake models namespace.

    Returns:
        The provider under test.
    """
    gemini_provider = GeminiProvider(api_key=FAKE_API_KEY, model_id=FAKE_MODEL_ID)
    gemini_provider._client = FakeClient(aio=FakeAio(models=fake_models))

    return gemini_provider


async def collect(gemini_provider: GeminiProvider) -> list:
    """Run one turn with a single user message and gather its events.

    Args:
        gemini_provider: the provider under test.

    Returns:
        The events in order.
    """
    events = []
    async for event in gemini_provider.stream_turn("prompt", [UserMessage(text="hi")], []):
        events.append(event)

    return events


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the retry sleep with a recorder so tests run instantly."""
    recorded_delays: list[float] = []

    async def record_delay(delay_seconds: float) -> None:
        recorded_delays.append(delay_seconds)

    monkeypatch.setattr(provider_module.asyncio, "sleep", record_delay)

    return recorded_delays


@pytest.mark.anyio
async def test_text_turn_streams_deltas_and_a_stop_finish_with_the_signature(
    no_sleep: list[float],
) -> None:
    """Text parts become deltas; the text signature lands in the finish state."""
    fake_models = FakeModels(
        stream_chunks=[
            types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(
                            parts=[types.Part(text="Hel", thought_signature=b"s")]
                        )
                    )
                ]
            ),
            types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(parts=[types.Part(text="lo")]),
                        finish_reason=types.FinishReason.STOP,
                    )
                ]
            ),
        ]
    )

    events = await collect(provider_with(fake_models))

    assert events[:2] == [TextDelta(text="Hel"), TextDelta(text="lo")]
    finished = events[-1]
    assert isinstance(finished, TurnFinished)
    assert finished.reason == FINISH_REASON_STOP
    assert finished.provider_state[THOUGHT_SIGNATURE_KEY] == "cw=="
    assert fake_models.requested_model_ids == [FAKE_MODEL_ID]


@pytest.mark.anyio
async def test_tool_call_turn_finishes_with_tool_calls(no_sleep: list[float]) -> None:
    """A streamed function call yields the request and the tool-calls finish reason."""
    call_part = types.Part(
        function_call=types.FunctionCall(id="c1", name="search_tickets", args={"query": "q"})
    )
    fake_models = FakeModels(
        stream_chunks=[
            types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(parts=[call_part]),
                        finish_reason=types.FinishReason.STOP,
                    )
                ]
            )
        ]
    )

    events = await collect(provider_with(fake_models))

    assert isinstance(events[0], ToolCallRequest)
    assert events[-1].reason == FINISH_REASON_TOOL_CALLS


@pytest.mark.anyio
async def test_transient_errors_are_retried_with_doubling_delays(no_sleep: list[float]) -> None:
    """Two quota errors, then success: the turn completes after two waits of 2 and 4 seconds."""
    fake_models = FakeModels(
        errors_to_raise=[transient_error(), transient_error()],
        stream_chunks=[
            types.GenerateContentResponse(
                candidates=[
                    types.Candidate(
                        content=types.Content(parts=[types.Part(text="ok")]),
                        finish_reason=types.FinishReason.STOP,
                    )
                ]
            )
        ],
    )

    events = await collect(provider_with(fake_models))

    assert events[0] == TextDelta(text="ok")
    assert no_sleep == [2.0, 4.0]
    assert len(fake_models.requested_model_ids) == 3


@pytest.mark.anyio
async def test_transient_error_on_every_attempt_becomes_a_provider_error(
    no_sleep: list[float],
) -> None:
    """After the last attempt the quota error is reported, not retried forever."""
    fake_models = FakeModels(errors_to_raise=[transient_error()] * MODEL_REQUEST_ATTEMPTS)

    with pytest.raises(ModelProviderError, match="quota"):
        await collect(provider_with(fake_models))

    assert len(fake_models.requested_model_ids) == MODEL_REQUEST_ATTEMPTS
    assert len(no_sleep) == MODEL_REQUEST_ATTEMPTS - 1


@pytest.mark.anyio
async def test_permanent_error_is_not_retried(no_sleep: list[float]) -> None:
    """A bad request is reported at once, with no sleep and no second attempt."""
    fake_models = FakeModels(errors_to_raise=[permanent_error()])

    with pytest.raises(ModelProviderError, match="bad request"):
        await collect(provider_with(fake_models))

    assert len(fake_models.requested_model_ids) == 1
    assert no_sleep == []


@pytest.mark.anyio
async def test_aclose_closes_the_sdk_client() -> None:
    """Closing the provider closes the SDK's HTTP client."""
    fake_models = FakeModels()
    gemini_provider = provider_with(fake_models)

    await gemini_provider.aclose()

    assert gemini_provider._client.aio.is_closed is True
