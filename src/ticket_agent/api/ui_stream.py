"""Encode agent events as the AI SDK UI message stream (server-sent events)."""

import json
from collections.abc import AsyncIterator, Mapping
from typing import Any
from uuid import uuid4

from fastapi.responses import StreamingResponse

from ticket_agent.agent.loop import AgentEvent, AssistantTextDelta, TurnInterrupted
from ticket_agent.constants.ui_stream import (
    FIELD_DELTA,
    FIELD_ERROR_TEXT,
    FIELD_ID,
    FIELD_MESSAGE_ID,
    FIELD_TYPE,
    PART_TYPE_ERROR,
    PART_TYPE_FINISH,
    PART_TYPE_START,
    PART_TYPE_TEXT_DELTA,
    PART_TYPE_TEXT_END,
    PART_TYPE_TEXT_START,
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


async def encode_ui_stream(agent_events: AsyncIterator[AgentEvent]) -> AsyncIterator[str]:
    """Translate the agent's events into the parts of one assistant message.

    Emits `start`, then one text block opened at the first fragment and closed before
    an error or at the end, then `finish` and the terminator. An interrupted turn
    produces an `error` part after the text received so far; the stream still finishes
    cleanly so the client keeps that text.

    Args:
        agent_events: the events of one `run_turn`.

    Yields:
        Server-sent event lines, in order.
    """
    message_id = uuid4().hex
    text_block_id = uuid4().hex
    is_text_open = False

    yield part_event({FIELD_TYPE: PART_TYPE_START, FIELD_MESSAGE_ID: message_id})

    async for agent_event in agent_events:
        if isinstance(agent_event, AssistantTextDelta):
            if not is_text_open:
                yield part_event({FIELD_TYPE: PART_TYPE_TEXT_START, FIELD_ID: text_block_id})
                is_text_open = True
            yield part_event(
                {
                    FIELD_TYPE: PART_TYPE_TEXT_DELTA,
                    FIELD_ID: text_block_id,
                    FIELD_DELTA: agent_event.text,
                }
            )
        elif isinstance(agent_event, TurnInterrupted):
            if is_text_open:
                yield part_event({FIELD_TYPE: PART_TYPE_TEXT_END, FIELD_ID: text_block_id})
                is_text_open = False
            yield part_event(
                {FIELD_TYPE: PART_TYPE_ERROR, FIELD_ERROR_TEXT: agent_event.error_text}
            )

    if is_text_open:
        yield part_event({FIELD_TYPE: PART_TYPE_TEXT_END, FIELD_ID: text_block_id})

    yield part_event({FIELD_TYPE: PART_TYPE_FINISH})
    yield sse_event(STREAM_TERMINATOR)


def ui_stream_response(agent_events: AsyncIterator[AgentEvent]) -> StreamingResponse:
    """Build the streaming HTTP response the AI SDK client expects.

    Args:
        agent_events: the events of one `run_turn`.

    Returns:
        A response with the protocol header, event-stream media type and encoded body.
    """
    encoded_events = encode_ui_stream(agent_events)
    headers = {UI_STREAM_HEADER_NAME: UI_STREAM_HEADER_VALUE}
    response = StreamingResponse(encoded_events, media_type=UI_STREAM_MEDIA_TYPE, headers=headers)

    return response
