"""`GET /api/tickets` lists exactly the caller's tickets."""

import httpx
import pytest

from tests.constants.seed import ACME_TICKET_IDS, GLOBEX_TICKET_IDS
from tests.helpers.requests import list_ticket_ids, tenant_headers
from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID


@pytest.mark.anyio
async def test_each_tenant_lists_its_own_seed_tickets(client: httpx.AsyncClient) -> None:
    """Acme gets its six, Globex its six, and every row names the calling tenant."""
    assert await list_ticket_ids(client, ACME_TENANT_ID) == ACME_TICKET_IDS
    assert await list_ticket_ids(client, GLOBEX_TENANT_ID) == GLOBEX_TICKET_IDS

    response = await client.get("/api/tickets", headers=tenant_headers(ACME_TENANT_ID))
    tenant_ids = {ticket["tenant_id"] for ticket in response.json()}
    assert tenant_ids == {ACME_TENANT_ID}
