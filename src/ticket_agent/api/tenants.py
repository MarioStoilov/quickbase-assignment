"""The tenant list the login screen offers. Unauthenticated by design."""

from fastapi import APIRouter
from pydantic import BaseModel

from ticket_agent.db.session import DatabaseSession
from ticket_agent.tenants.repository import TenantRepository

router = APIRouter()


class TenantResponse(BaseModel):
    """One tenant as shown in the login screen."""

    id: str
    display_name: str


@router.get("/api/tenants")
def list_tenants(session: DatabaseSession) -> list[TenantResponse]:
    """Return every seeded tenant so the login screen can offer them.

    Args:
        session: per-request database session.

    Returns:
        All tenants, ordered by display name.
    """
    tenant_repository = TenantRepository(session)
    tenants = tenant_repository.list_all()

    tenant_responses = []
    for tenant in tenants:
        tenant_response = TenantResponse(id=tenant.id, display_name=tenant.display_name)
        tenant_responses.append(tenant_response)

    return tenant_responses
