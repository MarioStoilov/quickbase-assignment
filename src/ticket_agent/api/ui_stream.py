"""Encode agent events as the AI SDK UI message stream (server-sent events)."""

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import uuid4

from fastapi.responses import StreamingResponse

from ticket_agent.agent.loop import (
    AgentEvent,
    AssistantTextDelta,
    ToolCallCompleted,
    ToolCallRequested,
    ToolResponseRequired,
    TurnInterrupted,
)
from ticket_agent.constants.ui_stream import (
    DATA_KEY_OPTIONS,
    DATA_KEY_TOOL_NAME,
    FIELD_DATA,
    FIELD_DELTA,
    FIELD_ERROR_TEXT,
    FIELD_ID,
    FIELD_INPUT,
    FIELD_MESSAGE_ID,
    FIELD_OUTPUT,
    FIELD_TOOL_CALL_ID,
    FIELD_TOOL_NAME,
    FIELD_TYPE,
    PART_TYPE_ERROR,
    PART_TYPE_FINISH,
    PART_TYPE_START,
    PART_TYPE_TEXT_DELTA,
    PART_TYPE_TEXT_END,
    PART_TYPE_TEXT_START,
    PART_TYPE_TOOL_INPUT_AVAILABLE,
    PART_TYPE_TOOL_OUTPUT_AVAILABLE,
    PART_TYPE_TOOL_RESPONSE_REQUIRED,
    SSE_DATA_PREFIX,
    SSE_EVENT_TERMINATOR,
    STREAM_TERMINATOR,
    UI_STREAM_HEADER_NAME,
    UI_STREAM_HEADER_VALUE,
    UI_STREAM_MEDIA_TYPE,
)


def sse_event(payload: str) -> str:
    """Wrap `payload` as one server-sent event line.

    Args:
        payload: the already-serialised data.

    Returns:
        The `data:` line with its terminating blank line.
    """
    event = f"{SSE_DATA_PREFIX}{payload}{SSE_EVENT_TERMINATOR}"

    return event


def part_event(part: Mapping[str, Any]) -> str:
    """Serialise one stream part as a server-sent event.

    Args:
        part: the part's fields, `type` included.

    Returns:
        The event line carrying the part as JSON.
    """
    payload = json.dumps(part)
    event = sse_event(payload)

    return event


class TextBlockTracker:
    """Opens and closes the text blocks of one assistant message as text comes and goes.

    Text from different model rounds is separated by tool parts, and the protocol wants
    each run of text in its own block with its own id.
    """

    def __init__(self) -> None:
        """Start with no block open."""
        self._open_block_id: str | None = None

    def delta_parts(self, text: str) -> list[Mapping[str, Any]]:
        """Return the parts for one fragment, opening a block first if none is open.

        Args:
            text: the fragment.

        Returns:
            A `text-start` part when a block is opened, then the `text-delta` part.
        """
        parts: list[Mapping[str, Any]] = []
        is_block_open = self._open_block_id is not None

        if not is_block_open:
            self._open_block_id = uuid4().hex
            parts.append({FIELD_TYPE: PART_TYPE_TEXT_START, FIELD_ID: self._open_block_id})

        parts.append(
            {FIELD_TYPE: PART_TYPE_TEXT_DELTA, FIELD_ID: self._open_block_id, FIELD_DELTA: text}
        )

        return parts

    def close_parts(self) -> list[Mapping[str, Any]]:
        """Return the part that closes the open block, or nothing when none is open.

        Returns:
            At most one `text-end` part.
        """
        is_block_open = self._open_block_id is not None
        if not is_block_open:
            return []

        closing_part = {FIELD_TYPE: PART_TYPE_TEXT_END, FIELD_ID: self._open_block_id}
        self._open_block_id = None

        return [closing_part]


def parts_for_event(
    agent_event: AgentEvent, text_blocks: TextBlockTracker
) -> list[Mapping[str, Any]]:
    """Translate one agent event into the stream parts it produces.

    Args:
        agent_event: the event from the loop.
        text_blocks: tracker of the open text block, shared across the message.

    Returns:
        The parts, in order; a tool or error event closes any open text block first.
    """
    if isinstance(agent_event, AssistantTextDelta):
        delta_parts = text_blocks.delta_parts(agent_event.text)
        return delta_parts

    parts = text_blocks.close_parts()

    if isinstance(agent_event, ToolCallRequested):
        parts.append(
            {
                FIELD_TYPE: PART_TYPE_TOOL_INPUT_AVAILABLE,
                FIELD_TOOL_CALL_ID: agent_event.call_id,
                FIELD_TOOL_NAME: agent_event.tool_name,
                FIELD_INPUT: dict(agent_event.arguments),
            }
        )
    elif isinstance(agent_event, ToolCallCompleted):
        parts.append(
            {
                FIELD_TYPE: PART_TYPE_TOOL_OUTPUT_AVAILABLE,
                FIELD_TOOL_CALL_ID: agent_event.call_id,
                FIELD_OUTPUT: dict(agent_event.result),
            }
        )
    elif isinstance(agent_event, ToolResponseRequired):
        payload = {
            FIELD_TOOL_CALL_ID: agent_event.call_id,
            DATA_KEY_TOOL_NAME: agent_event.tool_name,
            DATA_KEY_OPTIONS: list(agent_event.options),
        }
        parts.append({FIELD_TYPE: PART_TYPE_TOOL_RESPONSE_REQUIRED, FIELD_DATA: payload})
    elif isinstance(agent_event, TurnInterrupted):
        parts.append({FIELD_TYPE: PART_TYPE_ERROR, FIELD_ERROR_TEXT: agent_event.error_text})

    return parts


async def encode_ui_stream(agent_events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    """Translate the agent's events into the parts of one assistant message.

    Emits `start`, then the parts of each event with text grouped into blocks, then
    `finish` and the terminator. An interrupted turn produces an `error` part after the
    text received so far; the stream still finishes cleanly so the client keeps that
    text. A stream that stops on a tool awaiting the person's answer ends after the
    response-required part, with the tool call left without an output.

    Args:
        agent_events: the events of one loop run.

    Yields:
        Server-sent event lines, in order.
    """
    message_id = uuid4().hex
    text_blocks = TextBlockTracker()

    yield part_event({FIELD_TYPE: PART_TYPE_START, FIELD_MESSAGE_ID: message_id})

    async for agent_event in agent_events:
        parts = parts_for_event(agent_event, text_blocks)
        for part in parts:
            yield part_event(part)

    closing_parts = text_blocks.close_parts()
    for part in closing_parts:
        yield part_event(part)

    yield part_event({FIELD_TYPE: PART_TYPE_FINISH})
    yield sse_event(STREAM_TERMINATOR)


def ui_stream_response(agent_events: AsyncIterator[AgentEvent]) -> StreamingResponse:
    """Build the streaming HTTP response the AI SDK client expects.

    Args:
        agent_events: the events of one loop run.

    Returns:
        A response with the protocol header, event-stream media type and encoded body.
    """
    encoded_events = encode_ui_stream(agent_events)
    headers = {UI_STREAM_HEADER_NAME: UI_STREAM_HEADER_VALUE}
    response = StreamingResponse(encoded_events, media_type=UI_STREAM_MEDIA_TYPE, headers=headers)

    return response
