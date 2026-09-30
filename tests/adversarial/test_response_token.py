"""Attacks on the response route: the pending call id is the only token there is."""

import httpx
import pytest

from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    list_ticket_ids,
    respond_to_tool_call,
    send_and_parse,
)
from tests.helpers.turns import delete_call, text_turn, tool_turn
from ticket_agent.constants.conversations import (
    CONVERSATION_NOT_FOUND_DETAIL,
    NO_SUCH_PENDING_CALL_DETAIL,
)
from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID


async def frozen_on_delete(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider, call_id: str, ticket_id: int
) -> str:
    """Create an Acme conversation frozen on a delete of `ticket_id` under `call_id`.

    Args:
        client: the test client.
        scripted_provider: the fake model.
        call_id: the id the scripted model gives the call.
        ticket_id: the Acme ticket to delete.

    Returns:
        The conversation id.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call(call_id, ticket_id)]))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, f"delete {ticket_id}")

    return conversation_id


@pytest.mark.anyio
async def test_tool_response_cannot_be_given_by_another_tenant(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is a Globex user who knows an Acme conversation id and its pending
    call id.

    They approve the call as Globex. The conversation is looked up with the caller's
    tenant before the call is considered, so the answer is 404 and the delete does
    not run.
    """
    # An Acme conversation frozen on a delete of ticket 1.
    conversation_id = await frozen_on_delete(client, scripted_provider, "call-first", 1)

    # The approval as Globex.
    response = await respond_to_tool_call(
        client, GLOBEX_TENANT_ID, conversation_id, "call-first", "approve"
    )

    # Not found, and ticket 1 is still there.
    assert response.status_code == 404
    assert response.json() == {"detail": CONVERSATION_NOT_FOUND_DETAIL}
    assert 1 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
async def test_tool_response_cannot_be_given_with_another_conversations_call_id(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is an Acme user who holds a genuine call id from one conversation.

    They answer a different conversation with it. Only the call id stored as pending
    on that conversation is accepted, so the answer is 409 and neither delete runs.
    """
    # Two Acme conversations, each frozen on its own delete.
    first_id = await frozen_on_delete(client, scripted_provider, "call-first", 1)
    await frozen_on_delete(client, scripted_provider, "call-second", 2)

    # The first conversation answered with the second conversation's call id.
    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, first_id, "call-second", "approve"
    )

    # Refused as no such pending call, and both tickets are still there.
    assert response.status_code == 409
    assert response.json() == {"detail": NO_SUCH_PENDING_CALL_DETAIL}
    remaining_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert 1 in remaining_ids
    assert 2 in remaining_ids


@pytest.mark.anyio
async def test_tool_response_cannot_be_replayed(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is an Acme user who resends an approval that already ran.

    After the genuine approval the conversation is no longer frozen, so the replay is
    refused with 409 and the delete ran exactly once.
    """
    # An Acme conversation frozen on a delete of ticket 1, and the model's report.
    conversation_id = await frozen_on_delete(client, scripted_provider, "call-first", 1)
    scripted_provider.add_turn(text_turn("Deleted #1."))

    # The genuine approval, then the same answer again.
    genuine = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-first", "approve"
    )
    replay = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-first", "approve"
    )

    # The genuine answer ran the delete; the replay was refused; the model was asked once.
    assert genuine.status_code == 200
    assert replay.status_code == 409
    assert replay.json() == {"detail": NO_SUCH_PENDING_CALL_DETAIL}
    assert 1 not in await list_ticket_ids(client, ACME_TENANT_ID)
    assert len(scripted_provider.calls) == 2
