"""The tenant middleware: public paths, missing and unknown headers."""

import httpx
import pytest

from tests.constants.seed import UNKNOWN_TENANT_ID
from tests.helpers.requests import tenant_headers
from ticket_agent import __version__
from ticket_agent.constants.auth import UNAUTHORISED_DETAIL


@pytest.mark.anyio
async def test_health_and_tenants_need_no_header(client: httpx.AsyncClient) -> None:
    """The two public paths answer without a tenant and the tenant list is the seed."""
    health_response = await client.get("/api/health")
    tenants_response = await client.get("/api/tenants")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok", "version": __version__}
    assert tenants_response.status_code == 200
    tenant_ids = [tenant["id"] for tenant in tenants_response.json()]
    assert tenant_ids == ["acme", "globex"]


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/api/tickets", "/api/chat", "/api/chat/new"])
async def test_protected_paths_without_header_answer_401(
    client: httpx.AsyncClient, path: str
) -> None:
    """Every protected path refuses a request that names no tenant."""
    response = await client.get(path)

    assert response.status_code == 401
    assert response.json() == {"detail": UNAUTHORISED_DETAIL}


@pytest.mark.anyio
async def test_unknown_and_blank_tenants_get_the_same_401_as_a_missing_header(
    client: httpx.AsyncClient,
) -> None:
    """An unknown slug and a blank header are refused with the one shared message."""
    unknown_response = await client.get("/api/tickets", headers=tenant_headers(UNKNOWN_TENANT_ID))
    blank_response = await client.get("/api/tickets", headers=tenant_headers("   "))

    assert unknown_response.status_code == 401
    assert blank_response.status_code == 401
    assert unknown_response.json() == blank_response.json()


@pytest.mark.anyio
async def test_paths_outside_the_api_are_not_guarded(client: httpx.AsyncClient) -> None:
    """The API docs are served without a tenant; the middleware only guards /api."""
    response = await client.get("/docs")

    assert response.status_code == 200
