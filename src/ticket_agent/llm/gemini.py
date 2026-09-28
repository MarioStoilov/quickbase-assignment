"""Gemini adapter: the only module that imports `google.genai`.

Converts the provider-neutral history and declarations to the SDK's types, streams the
response and converts each chunk back into `ModelEvent`s. Automatic function calling is
disabled explicitly so the SDK never runs anything on its own.
"""

import asyncio
import base64
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from typing import Any
from uuid import uuid4

from google import genai
from google.genai import errors, types

from ticket_agent.constants.llm import (
    FINISH_REASON_BLOCKED,
    FINISH_REASON_LENGTH,
    FINISH_REASON_STOP,
    FINISH_REASON_TOOL_CALLS,
    GENERATED_CALL_ID_PREFIX,
    MODEL_REQUEST_ATTEMPTS,
    MODEL_RETRY_INITIAL_DELAY_SECONDS,
    RETRYABLE_STATUS_CODES,
    THOUGHT_SIGNATURE_KEY,
)
from ticket_agent.llm.conversation import (
    AssistantMessage,
    Message,
    ToolDeclaration,
    ToolResultMessage,
    UserMessage,
)
from ticket_agent.llm.events import ModelEvent, TextDelta, ToolCallRequest, TurnFinished
from ticket_agent.llm.provider import ModelProviderError


class GeminiProvider:
    """A `ModelProvider` backed by one Gemini model through Google AI Studio."""

    def __init__(self, api_key: str, model_id: str) -> None:
        """Create the SDK client for `api_key` and remember which model to call.

        Args:
            api_key: Google AI Studio key.
            model_id: Gemini model id, e.g. `gemini-3.8-flash`.
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


def config_for_turn(
    system_prompt: str, tool_declarations: Sequence[ToolDeclaration]
) -> types.GenerateContentConfig:
    """Build the request configuration: prompt, tools, no automatic function calling.

    Args:
        system_prompt: instructions sent as the system instruction.
        tool_declarations: tools to declare; when empty no tool is offered.

    Returns:
        The SDK configuration for one request.
    """
    function_declarations = []
    for declaration in tool_declarations:
        function_declaration = types.FunctionDeclaration(
            name=declaration.name,
            description=declaration.description,
            parameters_json_schema=dict(declaration.parameters_schema),
        )
        function_declarations.append(function_declaration)

    has_tools = len(function_declarations) > 0
    tools: list[types.Tool] | None = None
    if has_tools:
        tools = [types.Tool(function_declarations=function_declarations)]

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    return config


def contents_from_history(history: Sequence[Message]) -> list[types.Content]:
    """Convert the history to the SDK's content list.

    Consecutive tool results are merged into one user content with several function
    response parts, because Gemini expects the responses to one model turn together.

    Args:
        history: the conversation so far, oldest first.

    Returns:
        One `Content` per user or assistant message, one per run of tool results.
    """
    contents: list[types.Content] = []

    for message in history:
        is_tool_result = isinstance(message, ToolResultMessage)
        previous_content = contents[-1] if contents else None
        is_previous_tool_results = previous_content is not None and _holds_function_responses(
            previous_content
        )

        if is_tool_result and is_previous_tool_results:
            response_part = _function_response_part(message)
            previous_content.parts.append(response_part)
            continue

        content = _content_from_message(message)
        contents.append(content)

    return contents


def _holds_function_responses(content: types.Content) -> bool:
    """Report whether `content` is a run of function responses built earlier.

    Args:
        content: an SDK content already in the list.

    Returns:
        True when its first part is a function response.
    """
    has_parts = content.parts is not None and len(content.parts) > 0
    if not has_parts:
        return False

    first_part = content.parts[0]
    is_function_response = first_part.function_response is not None

    return is_function_response


def _content_from_message(message: Message) -> types.Content:
    """Convert one history message to an SDK content.

    Args:
        message: a user, assistant or tool-result message.

    Returns:
        The content with the role Gemini expects for that message kind.
    """
    if isinstance(message, UserMessage):
        text_part = types.Part.from_text(text=message.text)
        content = types.Content(role="user", parts=[text_part])
        return content

    if isinstance(message, AssistantMessage):
        parts: list[types.Part] = []
        has_text = message.text != ""
        if has_text:
            text_signature = signature_from_state(message.provider_state)
            text_part = types.Part(text=message.text, thought_signature=text_signature)
            parts.append(text_part)
        for tool_call in message.tool_calls:
            function_call = types.FunctionCall(
                id=tool_call.call_id, name=tool_call.tool_name, args=dict(tool_call.arguments)
            )
            call_signature = signature_from_state(tool_call.provider_state)
            call_part = types.Part(function_call=function_call, thought_signature=call_signature)
            parts.append(call_part)
        content = types.Content(role="model", parts=parts)
        return content

    response_part = _function_response_part(message)
    content = types.Content(role="user", parts=[response_part])

    return content


def _function_response_part(message: ToolResultMessage) -> types.Part:
    """Wrap one tool result as a function response part.

    Args:
        message: the tool result to hand back.

    Returns:
        The SDK part carrying the call id, tool name and result mapping.
    """
    function_response = types.FunctionResponse(
        id=message.call_id, name=message.tool_name, response=dict(message.result)
    )
    part = types.Part(function_response=function_response)

    return part


def events_from_chunk(chunk: types.GenerateContentResponse) -> Iterator[ModelEvent]:
    """Yield the text and tool-call events one streamed chunk carries.

    Args:
        chunk: one streamed response.

    Yields:
        `TextDelta` for each non-thought text part, `ToolCallRequest` for each function
        call part, in the order they appear.
    """
    has_candidates = chunk.candidates is not None and len(chunk.candidates) > 0
    if not has_candidates:
        return

    candidate = chunk.candidates[0]
    has_parts = candidate.content is not None and candidate.content.parts is not None
    if not has_parts:
        return

    for part in candidate.content.parts:
        is_thought = bool(part.thought)
        if is_thought:
            continue

        has_text = part.text is not None and part.text != ""
        if has_text:
            yield TextDelta(text=part.text)

        function_call = part.function_call
        has_function_call = function_call is not None
        if has_function_call:
            yield _tool_call_request_from(function_call, part.thought_signature)


def _tool_call_request_from(
    function_call: types.FunctionCall, thought_signature: bytes | None
) -> ToolCallRequest:
    """Convert an SDK function call to a `ToolCallRequest`, generating an id if absent.

    Args:
        function_call: the part's function call.
        thought_signature: the part's signature, kept in `provider_state` for resending.

    Returns:
        The provider-neutral request.
    """
    has_id = function_call.id is not None and function_call.id != ""
    call_id = function_call.id if has_id else f"{GENERATED_CALL_ID_PREFIX}{uuid4().hex}"
    tool_name = function_call.name or ""
    arguments = dict(function_call.args or {})
    provider_state = state_from_signature(thought_signature)
    request = ToolCallRequest(
        call_id=call_id, tool_name=tool_name, arguments=arguments, provider_state=provider_state
    )

    return request


def state_from_signature(thought_signature: bytes | None) -> dict[str, Any]:
    """Encode a signature as JSON-safe provider state.

    Args:
        thought_signature: raw bytes from a part, or None.

    Returns:
        A mapping holding the base64 text under `THOUGHT_SIGNATURE_KEY`, or empty.
    """
    has_signature = thought_signature is not None and len(thought_signature) > 0
    if not has_signature:
        return {}

    encoded_signature = base64.b64encode(thought_signature).decode("ascii")
    state = {THOUGHT_SIGNATURE_KEY: encoded_signature}

    return state


def signature_from_state(provider_state: Mapping[str, Any]) -> bytes | None:
    """Decode the signature stored by `state_from_signature`.

    Args:
        provider_state: the mapping stored on a tool call or assistant message.

    Returns:
        The raw signature bytes, or None when the state holds none.
    """
    encoded_signature = provider_state.get(THOUGHT_SIGNATURE_KEY)
    has_signature = isinstance(encoded_signature, str) and encoded_signature != ""
    if not has_signature:
        return None

    thought_signature = base64.b64decode(encoded_signature)

    return thought_signature


def text_signature_of_chunk(chunk: types.GenerateContentResponse) -> str | None:
    """Return the base64 signature of a text part in `chunk`, if one carries it.

    Args:
        chunk: one streamed response.

    Returns:
        The encoded signature of the last signed text part, or None.
    """
    has_candidates = chunk.candidates is not None and len(chunk.candidates) > 0
    if not has_candidates:
        return None

    candidate = chunk.candidates[0]
    has_parts = candidate.content is not None and candidate.content.parts is not None
    if not has_parts:
        return None

    encoded_signature: str | None = None
    for part in candidate.content.parts:
        is_signed_text = part.function_call is None and part.thought_signature is not None
        if is_signed_text:
            state = state_from_signature(part.thought_signature)
            encoded_signature = state.get(THOUGHT_SIGNATURE_KEY)

    return encoded_signature


def finish_of_chunk(
    chunk: types.GenerateContentResponse,
) -> tuple[types.FinishReason | None, str | None]:
    """Read the finish reason and any block reason a chunk carries.

    Args:
        chunk: one streamed response.

    Returns:
        The candidate's finish reason (None until the last chunk) and, when the prompt
        itself was blocked, the block reason's name.
    """
    prompt_feedback = chunk.prompt_feedback
    is_prompt_blocked = prompt_feedback is not None and prompt_feedback.block_reason is not None
    if is_prompt_blocked:
        block_reason_name = prompt_feedback.block_reason.name
        return types.FinishReason.OTHER, f"prompt blocked: {block_reason_name}"

    has_candidates = chunk.candidates is not None and len(chunk.candidates) > 0
    if not has_candidates:
        return None, None

    candidate = chunk.candidates[0]
    finish_reason = candidate.finish_reason
    detail = candidate.finish_message

    return finish_reason, detail


def turn_finished_from(
    provider_reason: types.FinishReason | None,
    detail: str | None,
    has_requested_tools: bool,
    turn_state: Mapping[str, Any],
) -> TurnFinished:
    """Map the provider's finish reason to the neutral `TurnFinished` event.

    Args:
        provider_reason: the SDK's reason, or None when the stream ended without one.
        detail: the provider's message for a blocked or cut-off turn.
        has_requested_tools: whether any tool call was streamed this turn.
        turn_state: opaque state for the turn (the text part's signature, if any).

    Returns:
        `tool_calls` when tools were requested, `stop` for a natural end (or no reason),
        `length` for the token limit, `blocked` with `detail` for everything else.
    """
    if has_requested_tools:
        return TurnFinished(reason=FINISH_REASON_TOOL_CALLS, provider_state=turn_state)

    is_natural_stop = provider_reason is None or provider_reason == types.FinishReason.STOP
    if is_natural_stop:
        return TurnFinished(reason=FINISH_REASON_STOP, provider_state=turn_state)

    is_length_limit = provider_reason == types.FinishReason.MAX_TOKENS
    if is_length_limit:
        return TurnFinished(reason=FINISH_REASON_LENGTH, provider_state=turn_state)

    block_detail = detail or provider_reason.name
    finished = TurnFinished(
        reason=FINISH_REASON_BLOCKED, detail=block_detail, provider_state=turn_state
    )

    return finished
