"""HTTP calls the integration and adversarial tests make against the application."""

from typing import Any

import httpx

from tests.helpers.stream import ParsedStream, parse_stream
from ticket_agent.constants.auth import TENANT_HEADER_NAME


def tenant_headers(tenant_id: str) -> dict[str, str]:
    """Build the header that names the calling tenant.

    Args:
        tenant_id: the tenant slug.

    Returns:
        The headers for a request on that tenant's behalf.
    """
    headers = {TENANT_HEADER_NAME: tenant_id}

    return headers


def user_message_body(text: str) -> dict[str, Any]:
    """Build the body of a chat post in the AI SDK message shape.

    Args:
        text: what the person typed.

    Returns:
        The JSON body.
    """
    body = {"message": {"role": "user", "parts": [{"type": "text", "text": text}]}}

    return body


async def create_conversation(client: httpx.AsyncClient, tenant_id: str) -> str:
    """Create a conversation for the tenant and return its id.

    Args:
        client: the test client.
        tenant_id: the calling tenant.

    Returns:
        The server-generated id.
    """
    response = await client.post("/api/chat/new", headers=tenant_headers(tenant_id))
    assert response.status_code == 201, response.text
    conversation_id = response.json()["id"]

    return conversation_id


async def post_message(
    client: httpx.AsyncClient, tenant_id: str, conversation_id: str, text: str
) -> httpx.Response:
    """Post one user message to the conversation.

    Args:
        client: the test client.
        tenant_id: the calling tenant.
        conversation_id: the conversation to post to.
        text: what the person typed.

    Returns:
        The raw response; a stream when accepted, an error body otherwise.
    """
    response = await client.post(
        f"/api/chat/{conversation_id}",
        headers=tenant_headers(tenant_id),
        json=user_message_body(text),
    )

    return response


async def send_and_parse(
    client: httpx.AsyncClient, tenant_id: str, conversation_id: str, text: str
) -> ParsedStream:
    """Post one user message and parse the stream it answers with.

    Args:
        client: the test client.
        tenant_id: the calling tenant.
        conversation_id: the conversation to post to.
        text: what the person typed.

    Returns:
        The parsed stream.
    """
    response = await post_message(client, tenant_id, conversation_id, text)
    assert response.status_code == 200, response.text
    parsed_stream = parse_stream(response.text)

    return parsed_stream


async def read_conversation(
    client: httpx.AsyncClient, tenant_id: str, conversation_id: str
) -> dict[str, Any]:
    """Read the conversation back as its owner.

    Args:
        client: the test client.
        tenant_id: the calling tenant.
        conversation_id: the conversation to read.

    Returns:
        The response body.
    """
    response = await client.get(f"/api/chat/{conversation_id}", headers=tenant_headers(tenant_id))
    assert response.status_code == 200, response.text
    body = response.json()

    return body


async def respond_to_tool_call(
    client: httpx.AsyncClient,
    tenant_id: str,
    conversation_id: str,
    tool_call_id: str,
    option: str,
) -> httpx.Response:
    """Answer the pending tool call of the conversation.

    Args:
        client: the test client.
        tenant_id: the calling tenant.
        conversation_id: the frozen conversation.
        tool_call_id: the call id from the path.
        option: the option the person picks.

    Returns:
        The raw response; a stream when accepted, an error body otherwise.
    """
    response = await client.post(
        f"/api/chat/{conversation_id}/tool-calls/{tool_call_id}/response",
        headers=tenant_headers(tenant_id),
        json={"option": option},
    )

    return response


async def list_ticket_ids(client: httpx.AsyncClient, tenant_id: str) -> list[int]:
    """Return the ids of the tenant's tickets as the tickets route reports them.

    Args:
        client: the test client.
        tenant_id: the calling tenant.

    Returns:
        The ids, oldest first.
    """
    response = await client.get("/api/tickets", headers=tenant_headers(tenant_id))
    assert response.status_code == 200, response.text

    ticket_ids = []
    for ticket in response.json():
        ticket_ids.append(ticket["id"])

    return ticket_ids
