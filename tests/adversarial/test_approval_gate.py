"""Attacks that try to get a mutation executed without the person's click."""

import httpx
import pytest

from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    list_ticket_ids,
    post_message,
    read_conversation,
    send_and_parse,
    tenant_headers,
)
from tests.helpers.stream import parse_stream
from tests.helpers.turns import delete_call, text_turn, tool_turn, update_call
from ticket_agent.constants.conversations import CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
from ticket_agent.constants.seed import ACME_TENANT_ID, TARGET_FOREIGN_TICKET_ID

# Acme's seed ticket ids.
ACME_TICKET_IDS = [1, 2, 3, 4, 5, 6]


@pytest.mark.anyio
async def test_injected_delete_all_is_not_executed_without_approval(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the text of Acme ticket 3 and, through it, the model.

    The model obeys the brief's payload and requests a delete of every id it knows,
    Globex's 47 first, then Acme's own. The foreign id fails validation inline with a
    not-found result and no dialog; the first own-tenant call freezes the conversation
    and ends the stream. Nothing is deleted, the later calls are not even considered,
    and the model is not called again until the person answers.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    calls = [delete_call("call-47", TARGET_FOREIGN_TICKET_ID)]
    for ticket_id in ACME_TICKET_IDS:
        calls.append(delete_call(f"call-{ticket_id}", ticket_id))
    scripted_provider.add_turn(tool_turn(calls, leading_text="Deleting everything as instructed."))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "summarise ticket 3")

    foreign_output = stream.of_type("tool-output-available")
    assert len(foreign_output) == 1
    assert foreign_output[0]["toolCallId"] == "call-47"
    assert "not found" in foreign_output[0]["output"]["error"]
    required = stream.of_type("data-tool-response-required")[0]["data"]
    assert required["toolCallId"] == "call-1"
    assert await list_ticket_ids(client, ACME_TENANT_ID) == ACME_TICKET_IDS
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
    assert len(scripted_provider.calls) == 1


@pytest.mark.anyio
async def test_injected_approval_claim_does_not_skip_the_gate(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the text of Acme ticket 5, which claims approval was granted.

    The model believes it and calls mutate_ticket to close the ticket "without asking".
    The gate is decided by the tool's response options in code, not by anything in the
    history, so the call freezes the conversation like any other and the ticket keeps
    its status.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(
        tool_turn(
            [update_call("call-close", 5, {"status": "closed"})],
            leading_text="Approval is already granted, closing now.",
        )
    )

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "handle ticket 5")

    assert stream.of_type("data-tool-response-required")[0]["data"]["toolCallId"] == "call-close"
    assert stream.of_type("tool-output-available") == []
    tickets = await client.get("/api/tickets", headers=tenant_headers(ACME_TENANT_ID))
    ticket_five = [ticket for ticket in tickets.json() if ticket["id"] == 5][0]
    assert ticket_five["status"] == "in_progress"


@pytest.mark.anyio
async def test_model_cannot_self_approve(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's output entirely.

    The model streams text asserting that it approved the deletion, requests the
    delete, and a second scripted turn stands ready to "confirm" it. The only path
    that executes a gated tool is the response route with the pending call id, which
    the model cannot call: the conversation freezes, the second turn is never used,
    a new message is refused with 409, and the ticket still exists.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(
        tool_turn([delete_call("call-delete", 2)], leading_text="I approve this deletion myself.")
    )
    scripted_provider.add_turn(text_turn("Confirmed, ticket 2 is deleted."))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "delete 2")
    follow_up = await post_message(client, ACME_TENANT_ID, conversation_id, "is it gone?")

    assert stream.of_type("tool-output-available") == []
    assert follow_up.status_code == 409
    assert len(scripted_provider.calls) == 1
    assert 2 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
async def test_approved_execution_uses_frozen_arguments(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the response request's body.

    The person approved a delete of ticket 2; the response body also names ticket 4
    and a fresh arguments object. The route reads only the option and runs the call
    with the arguments stored when the model made it, so ticket 2 goes and ticket 4
    stays.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("call-delete", 2)]))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, "delete 2")
    scripted_provider.add_turn(text_turn("Deleted #2."))
    tampered_body = {
        "option": "approve",
        "ticket_id": 4,
        "arguments": {"ticket_id": 4, "action": "delete"},
    }

    response = await client.post(
        f"/api/chat/{conversation_id}/tool-calls/call-delete/response",
        headers=tenant_headers(ACME_TENANT_ID),
        json=tampered_body,
    )

    assert response.status_code == 200
    output = parse_stream(response.text).of_type("tool-output-available")[0]["output"]
    assert output["ticket_id"] == 2
    remaining_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert 2 not in remaining_ids
    assert 4 in remaining_ids
