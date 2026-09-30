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
async def test_list_is_newest_first_with_previews_status_and_only_own_rows(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """Two Acme conversations and one of Globex: Acme sees its two, newest first."""
    first_id = await create_conversation(client, ACME_TENANT_ID)
    scripted_provider.add_turn(text_turn("Hello"))
    await send_and_parse(client, ACME_TENANT_ID, first_id, "first message here")
    second_id = await create_conversation(client, ACME_TENANT_ID)
    await create_conversation(client, GLOBEX_TENANT_ID)

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    summaries = response.json()
    assert [summary["id"] for summary in summaries] == [second_id, first_id]
    assert summaries[0]["preview"] == ""
    assert summaries[1]["preview"] == "first message here"
    assert summaries[1]["status"] == CONVERSATION_STATUS_ACTIVE


@pytest.mark.anyio
async def test_list_cuts_long_previews_and_marks_frozen_conversations(
    client: httpx.AsyncClient, scripted_provider: ScriptedProvider
) -> None:
    """A long first message is cut at the bound, and a frozen conversation says so."""
    conversation_id = await create_conversation(client, ACME_TENANT_ID)
    long_text = "delete " * CONVERSATION_PREVIEW_MAX_LENGTH
    scripted_provider.add_turn(tool_turn([delete_call("c1", 1)]))
    await send_and_parse(client, ACME_TENANT_ID, conversation_id, long_text)

    response = await client.get("/api/chat", headers=tenant_headers(ACME_TENANT_ID))

    summary = response.json()[0]
    assert summary["status"] == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
    assert summary["preview"].endswith(CONVERSATION_PREVIEW_ELLIPSIS)
    assert len(summary["preview"]) <= CONVERSATION_PREVIEW_MAX_LENGTH + 1
