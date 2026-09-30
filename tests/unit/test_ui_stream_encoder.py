"""The encoder turns loop events into the AI SDK UI message stream."""

from collections.abc import AsyncIterator

import pytest

from tests.helpers.stream import ParsedStream, parse_stream
from ticket_agent.agent.loop import (
    AgentEvent,
    AssistantTextDelta,
    ToolCallCompleted,
    ToolCallRequested,
    ToolResponseRequired,
    TurnInterrupted,
)
from ticket_agent.api.ui_stream import encode_ui_stream, ui_stream_response
from ticket_agent.constants.ui_stream import UI_STREAM_HEADER_NAME, UI_STREAM_HEADER_VALUE


async def events_from(agent_events: list[AgentEvent]) -> AsyncIterator[AgentEvent]:
    """Yield the given events as the loop would.

    Args:
        agent_events: the events in order.

    Yields:
        Each event.
    """
    for agent_event in agent_events:
        yield agent_event


async def encode(agent_events: list[AgentEvent]) -> ParsedStream:
    """Run the encoder over the events and parse what it produced.

    Args:
        agent_events: the events in order.

    Returns:
        The parsed stream.
    """
    lines = []
    async for line in encode_ui_stream(events_from(agent_events)):
        lines.append(line)

    body = "".join(lines)
    parsed_stream = parse_stream(body)

    return parsed_stream


@pytest.mark.anyio
async def test_text_only_turn_is_one_text_block_between_start_and_finish() -> None:
    """Fragments share one block id and the stream ends with finish and the terminator."""
    stream = await encode([AssistantTextDelta(text="Hel"), AssistantTextDelta(text="lo")])

    assert stream.types() == [
        "start",
        "text-start",
        "text-delta",
        "text-delta",
        "text-end",
        "finish",
    ]
    assert stream.text() == "Hello"
    block_ids = {part["id"] for part in stream.parts if "id" in part}
    assert len(block_ids) == 1
    assert stream.is_terminated


@pytest.mark.anyio
async def test_tool_events_close_the_open_text_block_and_carry_their_fields() -> None:
    """A tool call after text closes the block; input and output parts carry the ids."""
    stream = await encode(
        [
            AssistantTextDelta(text="Looking"),
            ToolCallRequested(call_id="c1", tool_name="search_tickets", arguments={"query": "x"}),
            ToolCallCompleted(call_id="c1", result={"count": 0}),
            AssistantTextDelta(text="Nothing"),
        ]
    )

    assert stream.types() == [
        "start",
        "text-start",
        "text-delta",
        "text-end",
        "tool-input-available",
        "tool-output-available",
        "text-start",
        "text-delta",
        "text-end",
        "finish",
    ]
    input_part = stream.of_type("tool-input-available")[0]
    output_part = stream.of_type("tool-output-available")[0]
    assert input_part["toolCallId"] == "c1"
    assert input_part["toolName"] == "search_tickets"
    assert input_part["input"] == {"query": "x"}
    assert output_part["output"] == {"count": 0}


@pytest.mark.anyio
async def test_response_required_is_a_data_part_naming_the_options() -> None:
    """The custom part carries the call id, the tool name and the options."""
    stream = await encode(
        [
            ToolCallRequested(call_id="c2", tool_name="mutate_ticket", arguments={}),
            ToolResponseRequired(
                call_id="c2", tool_name="mutate_ticket", options=("approve", "reject")
            ),
        ]
    )

    data_part = stream.of_type("data-tool-response-required")[0]
    assert data_part["data"] == {
        "toolCallId": "c2",
        "toolName": "mutate_ticket",
        "options": ["approve", "reject"],
    }
    assert stream.types()[-1] == "finish"


@pytest.mark.anyio
async def test_interruption_keeps_the_text_and_ends_with_an_error_part() -> None:
    """Text streamed before the failure stays, then an error part, then a clean finish."""
    stream = await encode([AssistantTextDelta(text="partial"), TurnInterrupted(error_text="boom")])

    assert stream.text() == "partial"
    assert stream.of_type("error")[0]["errorText"] == "boom"
    assert stream.types()[-1] == "finish"
    assert stream.is_terminated


def test_response_carries_the_protocol_header_and_media_type() -> None:
    """The HTTP response announces the stream protocol the client expects."""
    response = ui_stream_response(events_from([]))

    assert response.headers[UI_STREAM_HEADER_NAME] == UI_STREAM_HEADER_VALUE
    assert response.media_type == "text/event-stream"
