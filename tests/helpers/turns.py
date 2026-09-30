"""Builders for the scripted model turns tests feed the fake provider."""

from collections.abc import Mapping
from typing import Any

from ticket_agent.constants.llm import (
    FINISH_REASON_BLOCKED,
    FINISH_REASON_STOP,
    FINISH_REASON_TOOL_CALLS,
)
from ticket_agent.llm.events import ModelEvent, TextDelta, ToolCallRequest, TurnFinished


def text_turn(text: str, provider_state: Mapping[str, Any] | None = None) -> list[ModelEvent]:
    """Script a turn in which the model answers with text and stops.

    Args:
        text: the whole answer; streamed as one fragment.
        provider_state: opaque state carried by the finish event, if any.

    Returns:
        The events of that turn.
    """
    state = dict(provider_state) if provider_state is not None else {}
    events: list[ModelEvent] = [
        TextDelta(text=text),
        TurnFinished(reason=FINISH_REASON_STOP, provider_state=state),
    ]

    return events


def tool_turn(
    calls: list[ToolCallRequest],
    leading_text: str = "",
    provider_state: Mapping[str, Any] | None = None,
) -> list[ModelEvent]:
    """Script a turn in which the model requests tool calls, optionally after some text.

    Args:
        calls: the calls, in the order the model makes them.
        leading_text: text streamed before the calls; empty for none.
        provider_state: opaque state carried by the finish event, if any.

    Returns:
        The events of that turn.
    """
    state = dict(provider_state) if provider_state is not None else {}
    events: list[ModelEvent] = []

    has_text = leading_text != ""
    if has_text:
        events.append(TextDelta(text=leading_text))

    events.extend(calls)
    events.append(TurnFinished(reason=FINISH_REASON_TOOL_CALLS, provider_state=state))

    return events


def blocked_turn(detail: str) -> list[ModelEvent]:
    """Script a turn the provider cut short with a safety block.

    Args:
        detail: the provider's own reason.

    Returns:
        The events of that turn: only the finish event.
    """
    events: list[ModelEvent] = [TurnFinished(reason=FINISH_REASON_BLOCKED, detail=detail)]

    return events


def search_call(call_id: str, query: str) -> ToolCallRequest:
    """Build a `search_tickets` request.

    Args:
        call_id: the id the model gives the call.
        query: the search text.

    Returns:
        The request event.
    """
    request = ToolCallRequest(
        call_id=call_id, tool_name="search_tickets", arguments={"query": query}
    )

    return request


def delete_call(call_id: str, ticket_id: int) -> ToolCallRequest:
    """Build a `mutate_ticket` delete request.

    Args:
        call_id: the id the model gives the call.
        ticket_id: the ticket to delete.

    Returns:
        The request event.
    """
    request = ToolCallRequest(
        call_id=call_id,
        tool_name="mutate_ticket",
        arguments={"ticket_id": ticket_id, "action": "delete"},
    )

    return request


def update_call(call_id: str, ticket_id: int, fields: Mapping[str, str]) -> ToolCallRequest:
    """Build a `mutate_ticket` update request.

    Args:
        call_id: the id the model gives the call.
        ticket_id: the ticket to change.
        fields: the columns to set.

    Returns:
        The request event.
    """
    request = ToolCallRequest(
        call_id=call_id,
        tool_name="mutate_ticket",
        arguments={"ticket_id": ticket_id, "action": "update", "fields": dict(fields)},
    )

    return request


def create_call(call_id: str, title: str, requester_email: str) -> ToolCallRequest:
    """Build a `create_ticket` request with a fixed description and priority.

    Args:
        call_id: the id the model gives the call.
        title: the new ticket's title.
        requester_email: the requester's address.

    Returns:
        The request event.
    """
    request = ToolCallRequest(
        call_id=call_id,
        tool_name="create_ticket",
        arguments={
            "title": title,
            "description": "Written by the scripted model.",
            "priority": "low",
            "requester_email": requester_email,
        },
    )

    return request
