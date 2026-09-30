"""Streamed Gemini chunks become provider-neutral events and finish reasons."""

import pytest
from google.genai import types

from ticket_agent.constants.llm import (
    FINISH_REASON_BLOCKED,
    FINISH_REASON_LENGTH,
    FINISH_REASON_STOP,
    FINISH_REASON_TOOL_CALLS,
    GENERATED_CALL_ID_PREFIX,
    THOUGHT_SIGNATURE_KEY,
)
from ticket_agent.llm.events import TextDelta, ToolCallRequest
from ticket_agent.llm.gemini.streaming import (
    events_from_chunk,
    finish_of_chunk,
    text_signature_of_chunk,
    turn_finished_from,
)


def chunk_with_parts(
    parts: list[types.Part], finish_reason: types.FinishReason | None = None
) -> types.GenerateContentResponse:
    """Build a streamed chunk carrying one candidate with `parts`.

    Args:
        parts: the candidate's parts.
        finish_reason: the candidate's finish reason, if this is the last chunk.

    Returns:
        The chunk.
    """
    candidate = types.Candidate(
        content=types.Content(role="model", parts=parts), finish_reason=finish_reason
    )
    chunk = types.GenerateContentResponse(candidates=[candidate])

    return chunk


def test_text_and_function_call_parts_become_events_and_thoughts_are_dropped() -> None:
    """Visible text and calls are yielded in order; a thought part yields nothing."""
    parts = [
        types.Part(text="hidden", thought=True),
        types.Part(text="Hello"),
        types.Part(
            function_call=types.FunctionCall(id="c1", name="search_tickets", args={"query": "x"})
        ),
    ]

    events = list(events_from_chunk(chunk_with_parts(parts)))

    assert events == [
        TextDelta(text="Hello"),
        ToolCallRequest(call_id="c1", tool_name="search_tickets", arguments={"query": "x"}),
    ]


def test_function_call_without_id_gets_a_generated_one() -> None:
    """A call the provider sent without an id is still addressable."""
    call_part = types.Part(function_call=types.FunctionCall(name="mutate_ticket", args={}))

    events = list(events_from_chunk(chunk_with_parts([call_part])))

    request = events[0]
    assert isinstance(request, ToolCallRequest)
    assert request.call_id.startswith(GENERATED_CALL_ID_PREFIX)


def test_function_call_signature_lands_in_the_provider_state() -> None:
    """A call part's thought signature is kept so it can be resent with the history."""
    call_part = types.Part(
        function_call=types.FunctionCall(id="c1", name="mutate_ticket", args={}),
        thought_signature=b"sig",
    )

    events = list(events_from_chunk(chunk_with_parts([call_part])))

    request = events[0]
    assert isinstance(request, ToolCallRequest)
    assert THOUGHT_SIGNATURE_KEY in request.provider_state


def test_chunk_without_candidates_yields_nothing() -> None:
    """A keep-alive chunk produces no event and no finish reason."""
    empty_chunk = types.GenerateContentResponse()

    assert list(events_from_chunk(empty_chunk)) == []
    assert finish_of_chunk(empty_chunk) == (None, None)
    assert text_signature_of_chunk(empty_chunk) is None


def test_text_signature_is_read_from_the_last_signed_text_part() -> None:
    """The signature on a text part is returned encoded; calls are not considered."""
    parts = [
        types.Part(text="a", thought_signature=b"first"),
        types.Part(text="b", thought_signature=b"second"),
        types.Part(function_call=types.FunctionCall(name="x", args={}), thought_signature=b"call"),
    ]

    encoded = text_signature_of_chunk(chunk_with_parts(parts))

    assert encoded == "c2Vjb25k"


def test_finish_of_chunk_reads_the_candidates_reason() -> None:
    """The last chunk's finish reason is read with no detail."""
    last_chunk = chunk_with_parts([types.Part(text="x")], types.FinishReason.STOP)

    assert finish_of_chunk(last_chunk) == (types.FinishReason.STOP, None)


def test_finish_of_chunk_reports_a_blocked_prompt_with_its_reason() -> None:
    """A blocked prompt is reported as OTHER with the block reason in the detail."""
    blocked_chunk = types.GenerateContentResponse(
        prompt_feedback=types.GenerateContentResponsePromptFeedback(
            block_reason=types.BlockedReason.SAFETY
        )
    )

    reason, detail = finish_of_chunk(blocked_chunk)

    assert reason == types.FinishReason.OTHER
    assert "SAFETY" in detail


@pytest.mark.parametrize(
    ("provider_reason", "detail", "has_requested_tools", "expected_reason", "expected_detail"),
    [
        (types.FinishReason.STOP, None, True, FINISH_REASON_TOOL_CALLS, None),
        (None, None, False, FINISH_REASON_STOP, None),
        (types.FinishReason.STOP, None, False, FINISH_REASON_STOP, None),
        (types.FinishReason.MAX_TOKENS, None, False, FINISH_REASON_LENGTH, None),
        (types.FinishReason.SAFETY, None, False, FINISH_REASON_BLOCKED, "SAFETY"),
        (
            types.FinishReason.OTHER,
            "prompt blocked: X",
            False,
            FINISH_REASON_BLOCKED,
            "prompt blocked: X",
        ),
    ],
)
def test_turn_finished_maps_the_providers_reason(
    provider_reason: types.FinishReason | None,
    detail: str | None,
    has_requested_tools: bool,
    expected_reason: str,
    expected_detail: str | None,
) -> None:
    """Tool calls win, STOP and no reason are stop, MAX_TOKENS is length, the rest is blocked."""
    finished = turn_finished_from(provider_reason, detail, has_requested_tools, {})

    assert finished.reason == expected_reason
    assert finished.detail == expected_detail


def test_turn_finished_carries_the_turn_state() -> None:
    """The opaque state handed in is attached to the finish event unchanged."""
    state = {THOUGHT_SIGNATURE_KEY: "abc"}

    finished = turn_finished_from(types.FinishReason.STOP, None, False, state)

    assert finished.provider_state == state
