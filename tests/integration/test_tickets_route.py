"""`GET /api/tickets` lists exactly the caller's tickets."""

import httpx
import pytest

from tests.constants.seed import ACME_TICKET_IDS, GLOBEX_TICKET_IDS
from tests.helpers.requests import tenant_headers
from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tenant_id", "expected_ids"),
    [(ACME_TENANT_ID, ACME_TICKET_IDS), (GLOBEX_TENANT_ID, GLOBEX_TICKET_IDS)],
)
async def test_each_tenant_lists_its_own_seed_tickets(
    client: httpx.AsyncClient, tenant_id: str, expected_ids: list[int]
) -> None:
    """A tenant gets exactly its seed rows, and every row names that tenant."""
    response = await client.get("/api/tickets", headers=tenant_headers(tenant_id))

    assert response.status_code == 200
    assert [ticket["id"] for ticket in response.json()] == expected_ids
    assert {ticket["tenant_id"] for ticket in response.json()} == {tenant_id}
