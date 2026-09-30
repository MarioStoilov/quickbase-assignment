"""Attacks that try to reach across tenants, through the model or through the API."""

import httpx
import pytest

from tests.constants.seed import FOREIGN_SECRET_FRAGMENTS, GLOBEX_TICKET_IDS, UNKNOWN_TENANT_ID
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
from tests.helpers.turns import (
    create_call,
    delete_call,
    lookup_call,
    search_call,
    text_turn,
    tool_turn,
)
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


@pytest.mark.anyio
async def test_search_never_returns_other_tenant_tickets(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's tool arguments (through an injected ticket text).

    They make the model search for Globex's confidential ticket 47 from an Acme
    conversation by the wording of its title. The repository puts the caller's tenant
    in every WHERE clause and the tool takes the tenant from the context, never from
    the arguments, so the search finds nothing and no fragment of ticket 47 appears
    anywhere in the stream or the stored history.
    """
    # An Acme conversation.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model searching for the foreign ticket's wording, then reporting.
    scripted_provider.add_turn(tool_turn([search_call("c1", "merger")]))
    scripted_provider.add_turn(text_turn("There is no such ticket here."))

    # The person asks for the foreign ticket outright.
    stream = await send_and_parse(
        client, ACME_TENANT_ID, conversation_id, "show the merger ticket from globex"
    )

    # The search matched nothing.
    output = stream.of_type("tool-output-available")[0]["output"]
    assert output["count"] == 0

    # Nothing of ticket 47 reached the stream or the stored history.
    stream_text = " ".join(str(part) for part in stream.parts)
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    stored_text = str(conversation["messages"])
    for fragment in FOREIGN_SECRET_FRAGMENTS:
        assert fragment not in stream_text
        assert fragment not in stored_text


@pytest.mark.anyio
async def test_search_by_foreign_id_finds_only_the_own_ticket_that_mentions_it(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's tool arguments (through an injected ticket text).

    They make the model search for "47" from an Acme conversation, hoping the id
    reaches Globex's ticket. The search is a text match within the caller's tenant, so
    the only hit is Acme's own ticket 3, whose injected description mentions "#47".
    """
    # An Acme conversation.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model searching for the foreign id, then reporting.
    scripted_provider.add_turn(tool_turn([search_call("c1", "47")]))
    scripted_provider.add_turn(text_turn("Only ticket 3 mentions 47."))

    # The person asks for ticket 47.
    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "show ticket 47")

    # The only match is Acme's ticket 3.
    output = stream.of_type("tool-output-available")[0]["output"]
    assert [ticket["id"] for ticket in output["tickets"]] == [3]


@pytest.mark.anyio
async def test_lookup_by_foreign_id_returns_nothing(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker controls the model's tool arguments (through an injected ticket text).

    They make the model fetch Globex's ticket 47 by its number from an Acme
    conversation. The lookup runs through the repository with the caller's tenant, so
    it finds nothing, and the model is told the ticket does not exist for it.
    """
    # An Acme conversation.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model fetching the foreign ticket by number, then reporting.
    scripted_provider.add_turn(tool_turn([lookup_call("c1", TARGET_FOREIGN_TICKET_ID)]))
    scripted_provider.add_turn(text_turn("There is no ticket 47 here."))

    # The person asks for ticket 47.
    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "show ticket 47")

    # The lookup returned nothing, and nothing of ticket 47 reached the stream.
    output = stream.of_type("tool-output-available")[0]["output"]
    assert output == {"tickets": [], "count": 0}
    stream_text = " ".join(str(part) for part in stream.parts)
    for fragment in FOREIGN_SECRET_FRAGMENTS:
        assert fragment not in stream_text


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
    # An Acme conversation.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model requesting a delete of Globex's ticket 47, then reporting the
    # result it gets.
    scripted_provider.add_turn(tool_turn([delete_call("c1", TARGET_FOREIGN_TICKET_ID)]))
    scripted_provider.add_turn(text_turn("Ticket 47 was not found."))

    # The person asks for the foreign delete.
    stream = await send_and_parse(client, ACME_TENANT_ID, conversation_id, "delete 47")

    # No dialog was raised; the call got the not-found error inline.
    assert stream.of_type("data-tool-response-required") == []
    output = stream.of_type("tool-output-available")[0]["output"]
    assert output == {"error": f"ticket {TARGET_FOREIGN_TICKET_ID} not found"}

    # The conversation is still active and Globex still has its ticket.
    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)
    assert conversation["status"] == CONVERSATION_STATUS_ACTIVE
    assert TARGET_FOREIGN_TICKET_ID in await list_ticket_ids(client, GLOBEX_TENANT_ID)


async def frozen_acme_conversation(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> str:
    """Create an Acme conversation frozen on a delete, for a Globex attacker to target.

    Args:
        client: the test client.
        scripted_provider: the fake model.

    Returns:
        The conversation id; its pending call id is `call-delete`.
    """
    acme_conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("call-delete", 1)]))
    await send_and_parse(client, ACME_TENANT_ID, acme_conversation_id, "delete 1")

    return acme_conversation_id


@pytest.mark.anyio
async def test_conversation_of_other_tenant_cannot_be_read(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is a Globex user who has learnt an Acme conversation id.

    They read it. The store looks the id up with the caller's tenant, so the answer is
    the same 404 an unknown id gets.
    """
    # An Acme conversation with history, and the attacker acting as Globex.
    acme_conversation_id = await frozen_acme_conversation(client, scripted_provider)

    # The read as Globex.
    response = await client.get(
        f"/api/chat/{acme_conversation_id}", headers=tenant_headers(GLOBEX_TENANT_ID)
    )

    # Not found, with the body that reveals nothing.
    assert response.status_code == 404
    assert response.json() == {"detail": CONVERSATION_NOT_FOUND_DETAIL}


@pytest.mark.anyio
async def test_conversation_of_other_tenant_cannot_be_posted_to(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is a Globex user who has learnt an Acme conversation id.

    They post a message into it. The ownership check runs before anything is stored
    or streamed, so the answer is 404 and the Acme history is unchanged.
    """
    # An Acme conversation with history, and the attacker acting as Globex.
    acme_conversation_id = await frozen_acme_conversation(client, scripted_provider)
    messages_before = (await read_conversation(client, ACME_TENANT_ID, acme_conversation_id))[
        "messages"
    ]

    # The post as Globex.
    response = await client.post(
        f"/api/chat/{acme_conversation_id}",
        headers=tenant_headers(GLOBEX_TENANT_ID),
        json=user_message_body("hi"),
    )

    # Not found, and nothing was written into the Acme conversation.
    assert response.status_code == 404
    assert response.json() == {"detail": CONVERSATION_NOT_FOUND_DETAIL}
    conversation = await read_conversation(client, ACME_TENANT_ID, acme_conversation_id)
    assert conversation["messages"] == messages_before


@pytest.mark.anyio
async def test_conversation_of_other_tenant_is_absent_from_the_list(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is a Globex user looking for other tenants' conversations.

    They list their conversations. The list query takes the caller's tenant, so the
    Acme conversation does not appear and the list is empty.
    """
    # An Acme conversation with history, and the attacker acting as Globex.
    await frozen_acme_conversation(client, scripted_provider)

    # The list as Globex.
    response = await client.get("/api/chat", headers=tenant_headers(GLOBEX_TENANT_ID))

    # Nothing of Acme's is listed.
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_pending_call_of_other_tenant_cannot_be_answered(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """The attacker is a Globex user who has learnt an Acme conversation id and its
    pending call id.

    They approve the call. The ownership check on the response route runs before the
    call is looked at, so the answer is 404, the call is still pending for Acme, and
    ticket 1 still exists.
    """
    # An Acme conversation frozen on a delete of ticket 1, and the attacker as Globex.
    acme_conversation_id = await frozen_acme_conversation(client, scripted_provider)

    # The approval as Globex.
    response = await respond_to_tool_call(
        client, GLOBEX_TENANT_ID, acme_conversation_id, "call-delete", "approve"
    )

    # Not found; the Acme conversation is still frozen on its call and ticket 1 exists.
    assert response.status_code == 404
    assert response.json() == {"detail": CONVERSATION_NOT_FOUND_DETAIL}
    conversation = await read_conversation(client, ACME_TENANT_ID, acme_conversation_id)
    assert conversation["pending_tool_call"]["call_id"] == "call-delete"
    assert 1 in await list_ticket_ids(client, ACME_TENANT_ID)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/tickets"), ("POST", "/api/chat/new"), ("GET", "/api/chat")],
)
async def test_unknown_tenant_is_rejected(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    """The attacker controls the tenant header.

    They send a slug that is not seeded, hoping for a default tenant or an error that
    reveals valid slugs. The middleware resolves the header against the tenants table
    before routing and answers 401 with one fixed message, whatever the route.
    """
    # A header naming a tenant that does not exist.
    headers = tenant_headers(UNKNOWN_TENANT_ID)

    # A protected route.
    response = await client.request(method, path, headers=headers)

    # Refused with the one message that reveals nothing.
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
    # An Acme conversation.
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    # Script the model proposing a ticket with an extra tenant_id argument naming Globex,
    # on top of the arguments the tool declares.
    honest_call = create_call("call-create", "Planted", "who@acme.example")
    planted_arguments = {**honest_call.arguments, "tenant_id": GLOBEX_TENANT_ID}
    planted_call = ToolCallRequest(
        call_id=honest_call.call_id, tool_name=honest_call.tool_name, arguments=planted_arguments
    )
    scripted_provider.add_turn(tool_turn([planted_call]))

    # The person asks for the ticket; the conversation freezes on the proposal.
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, "create it")

    # The person approves, and the model reports afterwards.
    scripted_provider.add_turn(text_turn("Created."))
    response = await respond_to_tool_call(
        client, ACME_TENANT_ID, conversation_id, "call-create", "approve"
    )

    # The ticket was created for Acme; Globex's list is exactly its seed rows.
    assert response.status_code == 200
    acme_ids = await list_ticket_ids(client, ACME_TENANT_ID)
    assert len(acme_ids) == 7
    assert await list_ticket_ids(client, GLOBEX_TENANT_ID) == GLOBEX_TICKET_IDS
