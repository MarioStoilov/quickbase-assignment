"""The tenant middleware: public paths, missing and unknown headers."""

import httpx
import pytest

from tests.constants.seed import UNKNOWN_TENANT_ID
from tests.helpers.requests import tenant_headers
from ticket_agent import __version__
from ticket_agent.constants.auth import UNAUTHORISED_DETAIL


@pytest.mark.anyio
async def test_health_needs_no_header(client: httpx.AsyncClient) -> None:
    """The liveness path answers without a tenant."""
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


@pytest.mark.anyio
async def test_tenant_list_needs_no_header_and_is_the_seed(client: httpx.AsyncClient) -> None:
    """The login screen's tenant list answers without a tenant and holds the seed."""
    response = await client.get("/api/tenants")

    assert response.status_code == 200
    tenant_ids = [tenant["id"] for tenant in response.json()]
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
@pytest.mark.parametrize("header_value", [UNKNOWN_TENANT_ID, "   "])
async def test_unknown_or_blank_tenant_gets_the_same_401_as_a_missing_header(
    client: httpx.AsyncClient, header_value: str
) -> None:
    """An unknown slug or a blank header is refused with the one shared message."""
    response = await client.get("/api/tickets", headers=tenant_headers(header_value))

    assert response.status_code == 401
    assert response.json() == {"detail": UNAUTHORISED_DETAIL}


@pytest.mark.anyio
async def test_paths_outside_the_api_are_not_guarded(client: httpx.AsyncClient) -> None:
    """The API docs are served without a tenant; the middleware only guards /api."""
    response = await client.get("/docs")

    assert response.status_code == 200
