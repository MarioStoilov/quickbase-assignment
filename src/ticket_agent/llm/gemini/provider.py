"""The Gemini `ModelProvider` implementation."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from google import genai
from google.genai import errors, types

from ticket_agent.constants.llm import (
    MODEL_REQUEST_ATTEMPTS,
    MODEL_RETRY_INITIAL_DELAY_SECONDS,
    RETRYABLE_STATUS_CODES,
    THOUGHT_SIGNATURE_KEY,
)
from ticket_agent.llm.conversation import Message, ToolDeclaration
from ticket_agent.llm.events import ModelEvent, ToolCallRequest
from ticket_agent.llm.gemini.conversion import config_for_turn, contents_from_history
from ticket_agent.llm.gemini.streaming import (
    events_from_chunk,
    finish_of_chunk,
    text_signature_of_chunk,
    turn_finished_from,
)
from ticket_agent.llm.provider import ModelProviderError


class GeminiProvider:
    """A `ModelProvider` backed by one Gemini model through Google AI Studio.

    Automatic function calling is disabled explicitly so the SDK never runs anything on
    its own; the provider only reports what the model asked for.
    """

    def __init__(self, api_key: str, model_id: str) -> None:
        """Create the SDK client for `api_key` and remember which model to call.

        Args:
            api_key: Google AI Studio key.
            model_id: Gemini model id, e.g. `gemini-3.5-flash-lite`.
        """
        self._client = genai.Client(api_key=api_key)
        self._model_id = model_id

    async def stream_turn(
        self,
        system_prompt: str,
        history: Sequence[Message],
        tool_declarations: Sequence[ToolDeclaration],
    ) -> AsyncIterator[ModelEvent]:
        """Stream one turn; see `ModelProvider.stream_turn` for the contract.

        Thought parts the model may emit are dropped, not shown as text. A function call
        that arrives without an id gets a generated one so it can be referred to later.
        A transient failure (quota window, model under high demand) is retried with
        doubling delays up to `MODEL_REQUEST_ATTEMPTS` times, but only while nothing has
        been yielded yet; a stream that breaks midway is reported as an error.

        Raises:
            ModelProviderError: the SDK raised an API error (quota, auth, bad request)
                or a transient error persisted through every attempt.
        """
        contents = contents_from_history(history)
        config = config_for_turn(system_prompt, tool_declarations)
        has_requested_tools = False
        provider_reason: types.FinishReason | None = None
        block_detail: str | None = None
        turn_state: dict[str, Any] = {}

        try:
            stream = await self._open_stream_with_retries(contents, config)
            async for chunk in stream:
                for event in events_from_chunk(chunk):
                    is_tool_call = isinstance(event, ToolCallRequest)
                    if is_tool_call:
                        has_requested_tools = True
                    yield event

                # A text part may carry the turn's thought signature; the last one seen
                # wins and is handed back with the assistant message.
                text_signature = text_signature_of_chunk(chunk)
                has_text_signature = text_signature is not None
                if has_text_signature:
                    turn_state[THOUGHT_SIGNATURE_KEY] = text_signature

                # The finish reason and any block reason arrive on the last chunk that
                # carries a candidate; earlier chunks leave them unset.
                candidate_reason, candidate_detail = finish_of_chunk(chunk)
                is_reason_known = candidate_reason is not None
                if is_reason_known:
                    provider_reason = candidate_reason
                    block_detail = candidate_detail
        except errors.APIError as api_error:
            raise ModelProviderError(f"model request failed: {api_error.message}") from api_error

        finished = turn_finished_from(
            provider_reason, block_detail, has_requested_tools, turn_state
        )

        yield finished

    async def _open_stream_with_retries(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> AsyncIterator[types.GenerateContentResponse]:
        """Start the streamed request, retrying transient failures with backoff.

        Args:
            contents: the converted history.
            config: the request configuration.

        Returns:
            The chunk iterator of the first attempt that was accepted.

        Raises:
            errors.APIError: a non-transient error, or a transient one on the last attempt.
        """
        delay_seconds = MODEL_RETRY_INITIAL_DELAY_SECONDS

        for attempt_number in range(1, MODEL_REQUEST_ATTEMPTS + 1):
            is_last_attempt = attempt_number == MODEL_REQUEST_ATTEMPTS

            try:
                stream = await self._client.aio.models.generate_content_stream(
                    model=self._model_id, contents=contents, config=config
                )
                return stream
            except errors.APIError as api_error:
                is_transient = api_error.code in RETRYABLE_STATUS_CODES
                if not is_transient or is_last_attempt:
                    raise

            await asyncio.sleep(delay_seconds)
            delay_seconds = delay_seconds * 2

        raise AssertionError("unreachable: every attempt returns or raises")
