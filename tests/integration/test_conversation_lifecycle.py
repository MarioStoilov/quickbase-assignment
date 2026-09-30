"""Create, read and list conversations; unknown and foreign ids answer alike."""

import httpx
import pytest

from tests.constants.fixtures import UUID_HEX_LENGTH
from tests.fakes.scripted_provider import ScriptedProvider
from tests.helpers.requests import (
    create_conversation,
    read_conversation,
    send_and_parse,
    tenant_headers,
)
from tests.helpers.turns import delete_call, text_turn, tool_turn
from ticket_agent.constants.conversations import (
    CONVERSATION_NOT_FOUND_DETAIL,
    CONVERSATION_PREVIEW_ELLIPSIS,
    CONVERSATION_PREVIEW_MAX_LENGTH,
    CONVERSATION_STATUS_ACTIVE,
    CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE,
)
from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID


@pytest.mark.anyio
async def test_create_returns_an_id_the_owner_can_read_back(client: httpx.AsyncClient) -> None:
    """A new conversation is empty, active, and bound to the caller."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)

    conversation = await read_conversation(client, ACME_TENANT_ID, conversation_id)

    assert len(conversation_id) == UUID_HEX_LENGTH
    assert conversation["tenant_id"] == ACME_TENANT_ID
    assert conversation["status"] == CONVERSATION_STATUS_ACTIVE
    assert conversation["messages"] == []
    assert conversation["pending_tool_call"] is None


@pytest.mark.anyio
async def test_unknown_and_foreign_ids_answer_the_same_404(client: httpx.AsyncClient) -> None:
    """Reading Globex's conversation as Acme looks exactly like reading a made-up id."""
    globex_conversation_id = await create_conversation(client, GLOBEX_TENANT_ID)

    foreign_response = await client.get(
        f"/api/chat/{globex_conversation_id}", headers=tenant_headers(ACME_TENANT_ID)
    )
    unknown_response = await client.get(
        "/api/chat/no-such-id", headers=tenant_headers(ACME_TENANT_ID)
    )

    assert foreign_response.status_code == 404
    assert unknown_response.status_code == 404
    assert (
        foreign_response.json()
        == unknown_response.json()
        == {"detail": CONVERSATION_NOT_FOUND_DETAIL}
    )


@pytest.mark.anyio
async def test_list_is_empty_for_a_fresh_tenant(client: httpx.AsyncClient) -> None:
    """Before any conversation exists the list is an empty array."""
    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.anyio
async def test_list_is_newest_first(client: httpx.AsyncClient) -> None:
    """Two conversations are listed with the later one first."""
    first_id = await create_conversation(client, ACME_TENANT_ID)
    second_id = await create_conversation(client, ACME_TENANT_ID)

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    assert [summary["id"] for summary in response.json()] == [second_id, first_id]


@pytest.mark.anyio
async def test_list_carries_the_first_user_message_as_preview(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A conversation with a message previews it; an untouched one previews nothing."""
    written_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(text_turn("Hello"))
    await send_and_parse(client, ACME_TENANT_ID, written_id, "first message here")
    untouched_id = await create_conversation(client, ACME_TENANT_ID)

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    previews_by_id = {summary["id"]: summary["preview"] for summary in response.json()}
    assert previews_by_id[written_id] == "first message here"
    assert previews_by_id[untouched_id] == ""


@pytest.mark.anyio
async def test_list_excludes_other_tenants_conversations(client: httpx.AsyncClient) -> None:
    """Globex's conversation never appears in Acme's list."""
    acme_id = await create_conversation(client, ACME_TENANT_ID)
    await create_conversation(client, GLOBEX_TENANT_ID)

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    assert [summary["id"] for summary in response.json()] == [acme_id]


@pytest.mark.anyio
async def test_list_cuts_long_previews_at_the_bound(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A long first message is cut at the bound and marked."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    long_text = "word " * CONVERSATION_PREVIEW_MAX_LENGTH
    scripted_provider.add_turn(text_turn("Noted."))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, long_text)

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    preview = response.json()[0]["preview"]
    assert preview.endswith(CONVERSATION_PREVIEW_ELLIPSIS)
    assert len(preview) <= CONVERSATION_PREVIEW_MAX_LENGTH + len(CONVERSATION_PREVIEW_ELLIPSIS)


@pytest.mark.anyio
async def test_list_reports_a_frozen_conversation_as_waiting(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A conversation halted on a tool call carries the waiting status in the list."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(tool_turn([delete_call("c1", 1)]))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, "delete 1")

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    assert response.json()[0]["status"] == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
