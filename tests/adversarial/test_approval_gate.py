"""Attacks that try to get a mutation executed without the person's click."""

import httpx
import pytest

from tests.constants.seed import ACME_TICKET_IDS
from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    list_ticket_ids,
    read_conversation,
    send_and_parse,
    tenant_headers,
)
from tests.helpers.stream import parse_stream
from tests.helpers.turns import delete_call, text_turn, tool_turn, update_call
from ticket_agent.constants.conversations import CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
from ticket_agent.constants.seed import ACME_TENANT_ID


@pytest.mark.anyio
async def test_delete_all_is_not_executed_without_approval(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """
    We ask the model to delete all Acme tickets, but it does not do so without approval.
    The model is not called as the approval is still pending.
    Result: no batch delete was executed.
    """
    # An Acme conversation, as an Acme user would open it.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model obeying the payload: a delete of every Acme ticket, all requested
    # in the same turn.
    calls = []
    for ticket_id in ACME_TICKET_IDS:
        calls.append(delete_call(f"call-{ticket_id}", ticket_id))
    scripted_provider.add_turn(tool_turn(calls, leading_text="Deleting everything as instructed."))

    # The person asks something innocent; the injected text does the rest.
    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "summarise ticket 3")

    # No call got a result; the first one froze the conversation and ended the stream.
    assert stream.of_type("tool-output-available") == []
    required = stream.of_type("data-tool-response-required")[0]["data"]
    assert required["toolCallId"] == "call-1"
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE

    # Nothing was deleted, and the model was not asked again.
    assert await list_ticket_ids(client, ACME_TENANT_ID) == ACME_TICKET_IDS
    assert len(scripted_provider.calls) == 1


@pytest.mark.anyio
async def test_injected_approval_claim_does_not_skip_the_gate(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """
    We ask the model to close ticket 5, stating it has already been approved,
    but it does not do so without an approval call from the tenant.
    Result: approval is still asked, despite stated that it already has been granted.
    """
    # An Acme conversation.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model believing ticket 5's "approval already granted" text: it announces
    # the approval and requests the update in the same turn.
    scripted_provider.add_turn(
        tool_turn(
            [update_call("call-close", 5, {"status": "closed"})],
            leading_text="Approval is already granted, closing now.",
        )
    )

    # The person asks about the ticket.
    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "handle ticket 5")

    # The update froze the conversation instead of running: no output, a dialog request.
    assert stream.of_type("data-tool-response-required")[0]["data"]["toolCallId"] == "call-close"
    assert stream.of_type("tool-output-available") == []

    # Ticket 5 still has its seed status.
    tickets = await client.get("/api/tickets", headers=tenant_headers(ACME_TENANT_ID))
    ticket_five = [ticket for ticket in tickets.json() if ticket["id"] == 5][0]
    assert ticket_five["status"] == "in_progress"


@pytest.mark.anyio
async def test_approved_execution_uses_frozen_arguments(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """
    We ask the model to delete ticket 2. The response is a request for approval, but we find a way to
    inject a different ticket id into the approval response (id 4). The user is presented with a modal to
    delete ticket 4, while the original tool call was for ticket 2.
    Result: the approval is granted, but the tool call still deletes ticket 2. (I.E, we do not rely on the
    approval call to change the tool call's arguments.)
    """
    # An Acme conversation frozen on a delete of ticket 2, as the model proposed it.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("call-delete", 2)]))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, "delete 2")

    # The model's report once the call has a result.
    scripted_provider.add_turn(text_turn("Deleted #2."))

    # The answer carries the approval plus extra fields pointing at ticket 4.
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

    # The stored call ran: ticket 2 is gone and ticket 4 was never touched.
    assert response.status_code == 200
    output = parse_stream(response.text).of_type("tool-output-available")[0]["output"]
    assert output["ticket_id"] == 2
    remaining_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert 2 not in remaining_ids
    assert 4 in remaining_ids
