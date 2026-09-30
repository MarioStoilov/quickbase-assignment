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


@pytest.mark.anyio
async def test_tool_response_cannot_be_given_by_another_tenant_or_for_another_call_or_twice(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker knows an Acme conversation id and its pending call id.

    As Globex they try to approve it: 404, since the conversation is not theirs. As
    Acme they try a call id from another conversation: 409, since only the stored
    pending id is accepted. After the real approval they replay it: 409 again, since
    the conversation is no longer frozen. The delete runs exactly once.
    """
    # Two Acme conversations, each frozen on a delete of a different ticket, so that a
    # genuine call id from one can be tried against the other.
    first_id = await create_conversation(client, ACME_TENANT_ID)
    second_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("call-first", 1)]))
    await send_and_parse(client, ACME_TENANT_ID, first_id, "delete 1")
    scripted_provider.add_turn(tool_turn([delete_call("call-second", 2)]))
    await send_and_parse(client, ACME_TENANT_ID, second_id, "delete 2")

    # As Globex, approve the first conversation's call; as Acme, approve the first
    # conversation with the second conversation's call id.
    by_globex = await respond_to_tool_call(
        client, GLOBEX_TENANT_ID, first_id, "call-first", "approve"
    )
    other_call = await respond_to_tool_call(
        client, ACME_TENANT_ID, first_id, "call-second", "approve"
    )

    # The foreign tenant gets not-found, the wrong call id gets the pending-call
    # refusal, and ticket 1 is still there.
    assert by_globex.status_code == 404
    assert by_globex.json() == {"detail": CONVERSATION_NOT_FOUND_DETAIL}
    assert other_call.status_code == 409
    assert other_call.json() == {"detail": NO_SUCH_PENDING_CALL_DETAIL}
    assert 1 in await list_ticket_ids(client, ACME_TENANT_ID)

    # The genuine approval by the owner, followed by a replay of the same answer.
    scripted_provider.add_turn(text_turn("Deleted #1."))
    genuine = await respond_to_tool_call(client, ACME_TENANT_ID, first_id, "call-first", "approve")
    replay = await respond_to_tool_call(client, ACME_TENANT_ID, first_id, "call-first", "approve")

    # The genuine answer ran the delete once; the replay was refused; ticket 2, pending
    # in the other conversation, is untouched.
    assert genuine.status_code == 200
    assert replay.status_code == 409
    remaining_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert 1 not in remaining_ids
    assert 2 in remaining_ids
