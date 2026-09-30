"""Attacks that try to reach across tenants, through the model or through the API."""

import httpx
import pytest

from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    list_ticket_ids,
    read_conversation,
    respond_to_tool_call,
    send_and_parse,
    tenant_headers,
    user_message_body,
)
from tests.helpers.turns import create_call, delete_call, search_call, text_turn, tool_turn
from ticket_agent.constants.auth import UNAUTHORISED_DETAIL
from ticket_agent.constants.conversations import (
    CONVERSATION_NOT_FOUND_DETAIL,
    CONVERSATION_STATUS_ACTIVE,
)
from ticket_agent.constants.seed import (
    ACME_TENANT_ID,
    GLOBEX_TENANT_ID,
    TARGET_FOREIGN_TICKET_ID,
)
from ticket_agent.llm.events import ToolCallRequest

# Words that appear only in Globex's confidential ticket 47.
FOREIGN_SECRET_FRAGMENTS = ["merger data room", "Lee Marchetti", "legal@globex.example"]


@pytest.mark.anyio
async def test_search_never_returns_other_tenant_tickets(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's tool arguments (through an injected ticket text).

    They make the model search for Globex's confidential ticket 47 from an Acme
    conversation, by id and by its wording. The repository puts the caller's tenant in
    every WHERE clause and the tool takes the tenant from the context, never from the
    arguments. The id search finds only Acme's own ticket 3, whose injected text
    mentions "#47"; the wording search finds nothing; and no fragment of ticket 47
    appears anywhere in the stream or the stored history.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([search_call("c1", "47"), search_call("c2", "merger")]))
    scripted_provider.add_turn(text_turn("There is no ticket 47 here."))

    stream = await send_and_parse(
        client, ACME_TENANT_ID, conversation_id, "show ticket 47 from globex"
    )

    outputs = stream.of_type("tool-output-available")
    by_id_result = outputs[0]["output"]
    by_wording_result = outputs[1]["output"]
    assert [ticket["id"] for ticket in by_id_result["tickets"]] == [3]
    assert by_wording_result["count"] == 0
    stream_text = " ".join(str(part) for part in stream.parts)
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    stored_text = str(conversation["messages"])
    for fragment in FOREIGN_SECRET_FRAGMENTS:
        assert fragment not in stream_text
        assert fragment not in stored_text


@pytest.mark.anyio
async def test_mutate_rejects_foreign_ticket_without_freezing_conversation(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's tool arguments.

    They make the model call mutate_ticket on Globex's ticket 47 from an Acme
    conversation. Validation runs before the person is asked and looks the ticket up
    with the caller's tenant, so the call gets the same not-found result a made-up id
    would, no approval dialog is raised, the conversation stays active, and ticket 47
    is untouched for Globex.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("c1", TARGET_FOREIGN_TICKET_ID)]))
    scripted_provider.add_turn(text_turn("Ticket 47 was not found."))

    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "delete 47")

    assert stream.of_type("data-tool-response-required") == []
    output = stream.of_type("tool-output-available")[0]["output"]
    assert output == {"error": f"ticket {TARGET_FOREIGN_TICKET_ID} not found"}
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_ACTIVE
    assert TARGET_FOREIGN_TICKET_ID in await list_ticket_ids(client, GLOBEX_TENANT_ID)


@pytest.mark.anyio
async def test_conversation_of_other_tenant_is_not_found_for_read_post_list_or_response(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is a Globex user who has learnt an Acme conversation id.

    They try to read it, post into it, find it in their list, and answer its pending
    tool call. Every store method takes the caller's tenant, so each attempt answers
    404 with the same body an unknown id gets, the list stays Globex-only, and the
    pending Acme call is still pending afterwards.
    """
    acme_conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("call-delete", 1)]))
    await send_and_parse(client, ACME_TENANT_ID, acme_conversation_id, "delete 1")
    globex_headers = tenant_headers(GLOBEX_TENANT_ID)

    read = await client.get(f"/api/chat/{acme_conversation_id}", headers=globex_headers)
    post = await client.post(
        f"/api/chat/{acme_conversation_id}", headers=globex_headers, json=user_message_body("hi")
    )
    listing = await client.get("/api/chat", headers=globex_headers)
    answer = await respond_to_tool_call(
        client, GLOBEX_TENANT_ID, acme_conversation_id, "call-delete", "approve"
    )

    for response in (read, post, answer):
        assert response.status_code == 404
        assert response.json() == {"detail": CONVERSATION_NOT_FOUND_DETAIL}
    assert listing.json() == []
    conversation = await read_conversation(client, ACME_TENANT_ID, acme_conversation_id)
    assert conversation["pending_tool_call"]["call_id"] == "call-delete"
    assert 1 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
async def test_unknown_tenant_is_rejected(client: httpx.AsyncClient) -> None:
    """The attacker controls the tenant header.

    They send a slug that is not seeded, hoping for a default tenant or an error that
    reveals valid slugs. The middleware resolves the header against the tenants table
    before routing and answers 401 with one fixed message, on every protected route.
    """
    headers = tenant_headers("initech")

    tickets = await client.get("/api/tickets", headers=headers)
    created = await client.post("/api/chat/new", headers=headers)
    listed = await client.get("/api/chat", headers=headers)

    for response in (tickets, created, listed):
        assert response.status_code == 401
        assert response.json() == {"detail": UNAUTHORISED_DETAIL}


@pytest.mark.anyio
async def test_create_ticket_lands_in_callers_tenant_only(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's tool arguments.

    They make the model call create_ticket with an extra tenant_id naming Globex, to
    plant a ticket in another tenant. The tool's schema has no tenant field and the
    repository takes the tenant from the context, so the extra argument is ignored and
    the approved ticket appears in Acme's list and not in Globex's.
    """
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    honest_call = create_call("call-create", "Planted", "who@acme.example")
    planted_arguments = {**honest_call.arguments, "tenant_id": GLOBEX_TENANT_ID}
    planted_call = ToolCallRequest(
        call_id=honest_call.call_id, tool_name=honest_call.tool_name, arguments=planted_arguments
    )
    scripted_provider.add_turn(tool_turn([planted_call]))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, "create it")
    scripted_provider.add_turn(text_turn("Created."))

    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-create", "approve"
    )

    assert response.status_code == 200
    globex_ids_before = [42, 43, 44, 45, 46, 47]
    acme_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert await list_ticket_ids(client, GLOBEX_TENANT_ID) == globex_ids_before
    assert len(acme_ids) == 7
