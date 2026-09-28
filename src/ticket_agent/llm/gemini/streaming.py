"""Turn streamed Gemini chunks back into provider-neutral events."""

from collections.abc import Iterator, Mapping
from typing import Any
from uuid import uuid4

from google.genai import types

from ticket_agent.constants.llm import (
    FINISH_REASON_BLOCKED,
    FINISH_REASON_LENGTH,
    FINISH_REASON_STOP,
    FINISH_REASON_TOOL_CALLS,
    GENERATED_CALL_ID_PREFIX,
    THOUGHT_SIGNATURE_KEY,
)
from ticket_agent.llm.events import ModelEvent, TextDelta, ToolCallRequest, TurnFinished
from ticket_agent.llm.gemini.signatures import state_from_signature


def events_from_chunk(chunk: types.GenerateContentResponse) -> Iterator[ModelEvent]:
    """Yield the text and tool-call events one streamed chunk carries.

    Args:
        chunk: one streamed response.

    Yields:
        `TextDelta` for each non-thought text part, `ToolCallRequest` for each function
        call part, in the order they appear.
    """
    parts = _parts_of_chunk(chunk)

    for part in parts:
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


def _parts_of_chunk(chunk: types.GenerateContentResponse) -> list[types.Part]:
    """Return the parts of the first candidate, or an empty list when there are none.

    Args:
        chunk: one streamed response.

    Returns:
        The candidate's parts; empty for chunks that carry no content.
    """
    has_candidates = chunk.candidates is not None and len(chunk.candidates) > 0
    if not has_candidates:
        return []

    candidate = chunk.candidates[0]
    has_parts = candidate.content is not None and candidate.content.parts is not None
    if not has_parts:
        return []

    return candidate.content.parts


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


def text_signature_of_chunk(chunk: types.GenerateContentResponse) -> str | None:
    """Return the base64 signature of a text part in `chunk`, if one carries it.

    Args:
        chunk: one streamed response.

    Returns:
        The encoded signature of the last signed text part, or None.
    """
    parts = _parts_of_chunk(chunk)
    encoded_signature: str | None = None

    for part in parts:
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
