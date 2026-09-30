"""History and declarations become Gemini SDK types, signatures included."""

from google.genai import types

from tests.constants.provider import RAW_SIGNATURE
from ticket_agent.llm.conversation import (
    AssistantMessage,
    ToolCall,
    ToolDeclaration,
    ToolResultMessage,
    UserMessage,
)
from ticket_agent.llm.gemini.conversion import config_for_turn, contents_from_history
from ticket_agent.llm.gemini.signatures import signature_from_state, state_from_signature


def test_config_declares_tools_and_disables_automatic_calling() -> None:
    """The prompt, one function declaration per tool, and no SDK-side execution."""
    declaration = ToolDeclaration(
        name="search_tickets",
        description="find",
        parameters_schema={"type": "object", "properties": {}},
    )

    config = config_for_turn("be helpful", [declaration])

    assert config.system_instruction == "be helpful"
    assert config.tools[0].function_declarations[0].name == "search_tickets"
    assert config.automatic_function_calling.disable is True


def test_config_without_tools_offers_none() -> None:
    """A plain chat turn declares no tools at all."""
    config = config_for_turn("be helpful", [])

    assert config.tools is None


def test_history_maps_roles_and_merges_consecutive_tool_results() -> None:
    """User and model contents in order; two tool results share one user content."""
    call_one = ToolCall(call_id="c1", tool_name="search_tickets", arguments={"query": "a"})
    call_two = ToolCall(call_id="c2", tool_name="search_tickets", arguments={"query": "b"})
    history = [
        UserMessage(text="hello"),
        AssistantMessage(text="looking", tool_calls=(call_one, call_two)),
        ToolResultMessage(call_id="c1", tool_name="search_tickets", result={"count": 1}),
        ToolResultMessage(call_id="c2", tool_name="search_tickets", result={"count": 2}),
        AssistantMessage(text="done"),
    ]

    contents = contents_from_history(history)

    roles = [content.role for content in contents]
    assert roles == ["user", "model", "user", "model"]
    assert contents[0].parts[0].text == "hello"
    model_parts = contents[1].parts
    assert model_parts[0].text == "looking"
    assert model_parts[1].function_call.name == "search_tickets"
    assert model_parts[2].function_call.id == "c2"
    response_parts = contents[2].parts
    assert [part.function_response.id for part in response_parts] == ["c1", "c2"]
    assert response_parts[1].function_response.response == {"count": 2}


def test_signatures_travel_from_state_back_onto_the_parts() -> None:
    """The base64 state stored with a message is decoded onto the resent parts."""
    signed_call = ToolCall(
        call_id="c1",
        tool_name="search_tickets",
        arguments={},
        provider_state=state_from_signature(RAW_SIGNATURE),
    )
    history = [
        AssistantMessage(
            text="thinking",
            tool_calls=(signed_call,),
            provider_state=state_from_signature(RAW_SIGNATURE),
        )
    ]

    contents = contents_from_history(history)

    text_part, call_part = contents[0].parts
    assert text_part.thought_signature == RAW_SIGNATURE
    assert call_part.thought_signature == RAW_SIGNATURE


def test_assistant_message_without_text_has_only_call_parts() -> None:
    """An empty text produces no text part, so the model is not sent a blank."""
    call = ToolCall(call_id="c1", tool_name="search_tickets", arguments={})

    contents = contents_from_history([AssistantMessage(tool_calls=(call,))])

    assert len(contents[0].parts) == 1
    assert contents[0].parts[0].function_call is not None


def test_signature_state_round_trip_and_empty_cases() -> None:
    """Bytes become base64 state and back; empty or absent signatures give empty state."""
    state = state_from_signature(RAW_SIGNATURE)

    assert signature_from_state(state) == RAW_SIGNATURE
    assert state_from_signature(None) == {}
    assert state_from_signature(b"") == {}
    assert signature_from_state({}) is None
    assert signature_from_state({"thought_signature": ""}) is None


def test_part_types_are_the_sdk_types() -> None:
    """The conversion produces SDK content objects, which the client accepts as-is."""
    contents = contents_from_history([UserMessage(text="x")])

    assert isinstance(contents[0], types.Content)
