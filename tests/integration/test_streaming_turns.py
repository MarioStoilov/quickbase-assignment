"""Turns without a freeze: text, search, refusals, provider failures, the round bound."""

from pathlib import Path

import httpx
import pytest

from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    post_message,
    read_conversation,
    send_and_parse,
    tenant_headers,
)
from tests.helpers.stream import parse_stream
from tests.helpers.turns import blocked_turn, search_call, text_turn, tool_turn
from ticket_agent.constants.chat import (
    BLOCKED_TURN_ERROR_TEXT,
    EMPTY_MESSAGE_DETAIL,
    UNSUPPORTED_ROLE_DETAIL,
)
from ticket_agent.constants.conversations import CONVERSATION_STATUS_ACTIVE
from ticket_agent.constants.seed import ACME_TENANT_ID
from ticket_agent.constants.tools import TOOL_ROUND_LIMIT_ERROR, UNKNOWN_TOOL_ERROR
from ticket_agent.constants.ui_stream import UI_STREAM_HEADER_NAME, UI_STREAM_HEADER_VALUE
from ticket_agent.llm.conversation import AssistantMessage, ToolResultMessage, UserMessage
from ticket_agent.llm.events import TextDelta, ToolCallRequest
from ticket_agent.llm.provider import ModelProviderError
from ticket_agent.settings import Settings

# Opaque state the fake attaches to a call and a turn, to check it comes back.
CALL_STATE = {"thought_signature": "call-signature"}
TURN_STATE = {"thought_signature": "turn-signature"}

# A round bound small enough to hit with two scripted tool turns.
SMALL_ROUND_BOUND = 2


@pytest.mark.anyio
async def test_text_turn_streams_one_block_and_stores_both_messages(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The protocol header, the part sequence, the terminator, and the stored history."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(text_turn("Hello there"))

    response = await post_message(client, ACME_TENANT_ID, conversation_id, "hi")

    assert response.status_code == 200
    assert response.headers[UI_STREAM_HEADER_NAME] == UI_STREAM_HEADER_VALUE
    stream = parse_stream(response.text)
    assert stream.types() == ["start", "text-start", "text-delta", "text-end", "finish"]
    assert stream.text() == "Hello there"
    assert stream.is_terminated

    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant"]
    assert conversation["messages"][1]["content"]["text"] == "Hello there"


@pytest.mark.anyio
async def test_search_turn_runs_the_tool_and_returns_the_state_to_the_model(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The call and its Acme-only result stream, then the model's report; state round-trips."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    call = ToolCallRequest(
        call_id="c1", tool_name="search_tickets", arguments={"query": ""}, provider_state=CALL_STATE
    )
    scripted_provider.add_turn(tool_turn([call], provider_state=TURN_STATE))
    scripted_provider.add_turn(text_turn("You have six tickets."))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "list them")

    assert stream.types() == [
        "start",
        "tool-input-available",
        "tool-output-available",
        "text-start",
        "text-delta",
        "text-end",
        "finish",
    ]
    output = stream.of_type("tool-output-available")[0]["output"]
    assert [ticket["id"] for ticket in output["tickets"]] == [1, 2, 3, 4, 5, 6]

    second_call_history = scripted_provider.calls[1].history
    assert isinstance(second_call_history[0], UserMessage)
    assistant_message = second_call_history[1]
    assert isinstance(assistant_message, AssistantMessage)
    assert assistant_message.tool_calls[0].provider_state == CALL_STATE
    assert assistant_message.provider_state == TURN_STATE
    assert isinstance(second_call_history[2], ToolResultMessage)
    assert (
        scripted_provider.calls[1].tool_declarations == scripted_provider.calls[0].tool_declarations
    )


@pytest.mark.anyio
async def test_leading_text_before_a_tool_call_is_its_own_block(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """Text, then a call, then more text: two blocks around the tool parts."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([search_call("c1", "invoice")], leading_text="Looking. "))
    scripted_provider.add_turn(text_turn("Found #2."))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "invoice?")

    assert stream.types().count("text-start") == 2
    assert stream.text() == "Looking. Found #2."


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("body", "expected_detail"),
    [
        (
            {"message": {"role": "user", "parts": [{"type": "text", "text": "   "}]}},
            EMPTY_MESSAGE_DETAIL,
        ),
        (
            {"message": {"role": "user", "parts": [{"type": "file", "url": "x"}]}},
            EMPTY_MESSAGE_DETAIL,
        ),
        (
            {"message": {"role": "assistant", "parts": [{"type": "text", "text": "hi"}]}},
            UNSUPPORTED_ROLE_DETAIL,
        ),
    ],
)
async def test_unusable_messages_are_refused_with_400_and_nothing_is_stored(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider, body: dict, expected_detail: str
) -> None:
    """Blank text, no text part, or a non-user role never reach the model or the store."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    response = await client.post(
        f"/api/chat/{conversation_id}", headers=tenant_headers(ACME_TENANT_ID), json=body
    )

    assert response.status_code == 400
    assert response.json() == {"detail": expected_detail}
    assert scripted_provider.calls == []
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["messages"] == []


@pytest.mark.anyio
async def test_a_malformed_body_is_422(client: httpx.AsyncClient) -> None:
    """A body without the message envelope is rejected by validation."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    response = await client.post(
        f"/api/chat/{conversation_id}", headers=tenant_headers(ACME_TENANT_ID), json={"text": "hi"}
    )

    assert response.status_code == 422


@pytest.mark.anyio
async def test_provider_failure_mid_stream_keeps_the_text_and_stays_active(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """Text before the failure is streamed and stored, an error part follows, and the
    next turn works."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn([TextDelta(text="Partial "), ModelProviderError("quota hit")])
    scripted_provider.add_turn(text_turn("Back again."))

    failed_stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "hi")
    recovered_stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "again")

    assert failed_stream.text() == "Partial "
    assert failed_stream.of_type("error")[0]["errorText"] == "quota hit"
    assert failed_stream.types()[-1] == "finish"
    assert recovered_stream.text() == "Back again."
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    texts = [message["content"].get("text") for message in conversation["messages"]]
    assert texts == ["hi", "Partial ", "again", "Back again."]


@pytest.mark.anyio
async def test_provider_failure_before_any_text_stores_no_assistant_message(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A turn that produced nothing leaves only the user message behind."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(ModelProviderError("down"))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "hi")

    assert stream.of_type("error")[0]["errorText"] == "down"
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert [message["role"] for message in conversation["messages"]] == ["user"]


@pytest.mark.anyio
async def test_blocked_turn_is_reported_with_the_providers_reason(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A safety block ends the turn with the blocked text and the detail."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(blocked_turn("SAFETY"))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "hi")

    assert stream.of_type("error")[0]["errorText"] == f"{BLOCKED_TURN_ERROR_TEXT}: SAFETY"


@pytest.mark.anyio
async def test_unknown_tool_is_answered_inline_and_the_model_is_called_again(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A tool name the registry lacks yields an error result, not a crash or a freeze."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    bogus_call = ToolCallRequest(call_id="c1", tool_name="drop_everything", arguments={})
    scripted_provider.add_turn(tool_turn([bogus_call]))
    scripted_provider.add_turn(text_turn("I cannot do that."))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "hi")

    output = stream.of_type("tool-output-available")[0]["output"]
    assert output["error"].startswith(UNKNOWN_TOOL_ERROR)
    assert stream.text() == "I cannot do that."


@pytest.fixture
def bounded_settings(tmp_path: Path) -> Settings:
    """Settings with a round bound of two, over a fresh database file."""
    bounded = Settings(
        database_path=tmp_path / "bounded.db",
        gemini_api_key=None,
        max_tool_rounds=SMALL_ROUND_BOUND,
    )

    return bounded


@pytest.fixture
def settings(bounded_settings: Settings) -> Settings:
    """Override the shared settings so the app fixture uses the small bound."""
    return bounded_settings


@pytest.mark.anyio
async def test_round_bound_stops_a_model_that_keeps_calling_tools(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """After the bound, the stream ends with the limit error and the conversation stays usable."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    for round_index in range(SMALL_ROUND_BOUND + 1):
        scripted_provider.add_turn(tool_turn([search_call(f"c{round_index}", "")]))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "loop")

    assert stream.of_type("error")[0]["errorText"] == TOOL_ROUND_LIMIT_ERROR
    assert len(scripted_provider.calls) == SMALL_ROUND_BOUND
    assert len(stream.of_type("tool-output-available")) == SMALL_ROUND_BOUND
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_ACTIVE
