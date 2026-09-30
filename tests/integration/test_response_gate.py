"""The freeze on a tool with options and the route that answers it."""

import httpx
import pytest

from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    list_ticket_ids,
    post_message,
    read_conversation,
    respond_to_tool_call,
    send_and_parse,
    tenant_headers,
)
from tests.helpers.stream import ParsedStream, parse_stream
from tests.helpers.turns import create_call, delete_call, text_turn, tool_turn, update_call
from ticket_agent.constants.conversations import (
    AWAITING_TOOL_RESPONSE_DETAIL,
    CONVERSATION_STATUS_ACTIVE,
    CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE,
    INVALID_RESPONSE_OPTION_DETAIL,
    NO_SUCH_PENDING_CALL_DETAIL,
)
from ticket_agent.constants.seed import ACME_TENANT_ID


async def freeze_on_delete(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider, ticket_id: int
) -> tuple[str, ParsedStream]:
    """Start a conversation and drive it to a freeze on a delete of `ticket_id`.

    Args:
        client: the test client.
        scripted_provider: the fake model.
        ticket_id: the Acme ticket the scripted model asks to delete.

    Returns:
        The conversation id and the stream that ended on the freeze.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(
        tool_turn([delete_call("call-delete", ticket_id)], leading_text="Sure.")
    )
    stream = await send_and_parse(
        client, ACME_TENANT_ID, conversation_id, f"delete ticket {ticket_id}"
    )

    return conversation_id, stream


@pytest.mark.anyio
async def test_mutate_call_freezes_the_conversation_and_ends_the_stream(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The stream ends on the response-required part; the read shows the pending call."""
    conversation_id, stream = await freeze_on_delete(client, scripted_provider, 2)

    assert stream.types()[-3:] == ["tool-input-available", "data-tool-response-required", "finish"]
    assert stream.of_type("tool-output-available") == []
    required = stream.of_type("data-tool-response-required")[0]["data"]
    assert required == {
        "toolCallId": "call-delete",
        "toolName": "mutate_ticket",
        "options": ["approve", "reject"],
    }

    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
    assert conversation["pending_tool_call"] == {
        "call_id": "call-delete",
        "tool_name": "mutate_ticket",
        "arguments": {"ticket_id": 2, "action": "delete"},
        "options": ["approve", "reject"],
    }
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant"]
    assert 2 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
async def test_a_message_to_a_frozen_conversation_is_409_naming_the_call(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """While frozen, a new message is refused and nothing is stored or sent to the model."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 2)
    calls_before = len(scripted_provider.calls)

    response = await post_message(client, ACME_TENANT_ID, conversation_id, "never mind")

    assert response.status_code == 409
    assert response.json() == {"detail": f"{AWAITING_TOOL_RESPONSE_DETAIL}: call-delete"}
    assert len(scripted_provider.calls) == calls_before
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert len(conversation["messages"]) == 2


@pytest.mark.anyio
async def test_approve_runs_the_tool_and_continues_the_turn(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The result streams, the ticket is gone, the model reports, the conversation is active."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 2)
    scripted_provider.add_turn(text_turn("Deleted #2."))

    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-delete", "approve"
    )

    assert response.status_code == 200
    stream = parse_stream(response.text)
    assert stream.types() == [
        "start",
        "tool-output-available",
        "text-start",
        "text-delta",
        "text-end",
        "finish",
    ]
    output = stream.of_type("tool-output-available")[0]
    assert output["toolCallId"] == "call-delete"
    assert output["output"]["performed"] is True
    assert 2 not in await list_ticket_ids(client, ACME_TENANT_ID)
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_ACTIVE
    assert conversation["pending_tool_call"] is None
    roles = [message["role"] for message in conversation["messages"]]
    assert roles == ["user", "assistant", "tool", "assistant"]


@pytest.mark.anyio
async def test_reject_leaves_the_ticket_and_tells_the_model(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The declined result streams, the ticket stays, the model sees the declined result."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 2)
    scripted_provider.add_turn(text_turn("Not deleted."))

    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-delete", "reject"
    )

    stream = parse_stream(response.text)
    assert stream.of_type("tool-output-available")[0]["output"]["performed"] is False
    assert 2 in await list_ticket_ids(client, ACME_TENANT_ID)
    tool_result = scripted_provider.calls[1].history[-1]
    assert tool_result.result["performed"] is False


@pytest.mark.anyio
async def test_an_answer_for_a_call_that_is_not_pending_is_409(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A call id other than the stored pending one is refused and nothing runs."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 2)

    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-other", "approve"
    )

    assert response.status_code == 409
    assert response.json() == {"detail": NO_SUCH_PENDING_CALL_DETAIL}
    assert 2 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
async def test_an_option_the_tool_does_not_offer_is_400(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """An option outside the tool's response options is refused and nothing runs."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 2)

    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-delete", "maybe"
    )

    assert response.status_code == 400
    assert response.json() == {"detail": INVALID_RESPONSE_OPTION_DETAIL}
    assert 2 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
async def test_a_second_answer_to_an_answered_call_is_409(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """Once answered, the call is no longer pending, so a replay is refused."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 2)
    scripted_provider.add_turn(text_turn("Done."))
    first_answer = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-delete", "approve"
    )
    assert first_answer.status_code == 200

    replay = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-delete", "approve"
    )

    assert replay.status_code == 409
    assert len(scripted_provider.calls) == 2


@pytest.mark.anyio
async def test_create_turn_follows_the_same_gate_and_adds_the_ticket(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A create proposal freezes; approve adds an open ticket to the caller's list."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(
        tool_turn([create_call("call-create", "Printer jams", "pat@acme.example")])
    )
    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "new ticket")
    assert stream.of_type("data-tool-response-required")[0]["data"]["toolName"] == "create_ticket"

    scripted_provider.add_turn(text_turn("Created."))
    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-create", "approve"
    )

    output = parse_stream(response.text).of_type("tool-output-available")[0]["output"]
    assert output["performed"] is True
    ticket_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert output["ticket_id"] in ticket_ids
    tickets_response = await client.get("/api/tickets", headers=tenant_headers(ACME_TENANT_ID))
    new_ticket = [
        ticket for ticket in tickets_response.json() if ticket["id"] == output["ticket_id"]
    ][0]
    assert new_ticket["status"] == "open"
    assert new_ticket["title"] == "Printer jams"


@pytest.mark.anyio
async def test_two_gated_calls_in_one_turn_are_answered_one_at_a_time(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The second call waits for the first; the model is called once both have results."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(
        tool_turn(
            [update_call("call-first", 1, {"status": "closed"}), delete_call("call-second", 2)]
        )
    )
    first_stream = await send_and_parse(
        client, ACME_TENANT_ID, conversation_id, "close 1, delete 2"
    )
    assert (
        first_stream.of_type("data-tool-response-required")[0]["data"]["toolCallId"] == "call-first"
    )

    first_answer = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-first", "approve"
    )
    second_stream = parse_stream(first_answer.text)
    assert second_stream.types()[-2:] == ["data-tool-response-required", "finish"]
    assert (
        second_stream.of_type("data-tool-response-required")[0]["data"]["toolCallId"]
        == "call-second"
    )
    assert len(scripted_provider.calls) == 1

    scripted_provider.add_turn(text_turn("Closed #1, kept #2."))
    second_answer = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-second", "reject"
    )
    assert parse_stream(second_answer.text).text() == "Closed #1, kept #2."
    assert len(scripted_provider.calls) == 2
    assert 2 in await list_ticket_ids(client, ACME_TENANT_ID)
    tickets_response = await client.get("/api/tickets", headers=tenant_headers(ACME_TENANT_ID))
    first_ticket = [ticket for ticket in tickets_response.json() if ticket["id"] == 1][0]
    assert first_ticket["status"] == "closed"


@pytest.mark.anyio
async def test_read_while_frozen_is_the_reload_contract(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The stored assistant message carries the call and the pending call names its options."""
    conversation_id, _ = await freeze_on_delete(client, scripted_provider, 3)

    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)

    assistant_message = conversation["messages"][1]
    assert assistant_message["content"]["text"] == "Sure."
    stored_call = assistant_message["content"]["tool_calls"][0]
    assert stored_call["call_id"] == "call-delete"
    assert stored_call["arguments"] == {"ticket_id": 3, "action": "delete"}
    assert conversation["pending_tool_call"]["call_id"] == stored_call["call_id"]
    assert conversation["pending_tool_call"]["options"] == ["approve", "reject"]
