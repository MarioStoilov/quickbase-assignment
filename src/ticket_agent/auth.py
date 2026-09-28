"""Where the caller's tenant enters a request.

This is the only module that reads the `X-Tenant-ID` header. Handlers and tools receive
the resolved `Tenant` object from the `caller_tenant` dependency; nothing downstream
looks at headers or trusts a tenant id that came from anywhere else, including the
model's output.
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from ticket_agent.db.models import Tenant
from ticket_agent.db.session import DatabaseSession
from ticket_agent.tenants.repository import TenantRepository

# Name of the request header that stands in for real authentication.
TENANT_HEADER_NAME = "X-Tenant-ID"

# Error text for a missing and for an unknown header alike, so the response does not
# reveal which tenant slugs exist.
UNAUTHORISED_DETAIL = "missing or unknown tenant"


def caller_tenant(
    session: DatabaseSession,
    tenant_header: Annotated[str | None, Header(alias=TENANT_HEADER_NAME)] = None,
) -> Tenant:
    """Resolve the tenant named by the `X-Tenant-ID` header.

    Args:
        session: database session for the tenant lookup.
        tenant_header: raw header value, or None when absent.

    Returns:
        The `Tenant` row the header names.

    Raises:
        HTTPException: 401 when the header is absent or names no seeded tenant.
    """
    is_header_present = tenant_header is not None and tenant_header.strip() != ""

    if not is_header_present:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, UNAUTHORISED_DETAIL)

    tenant_repository = TenantRepository(session)
    tenant = tenant_repository.get(tenant_header.strip())
    is_known_tenant = tenant is not None

    if not is_known_tenant:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, UNAUTHORISED_DETAIL)

    return tenant


# Annotation handlers use to receive the resolved tenant.
CallerTenant = Annotated[Tenant, Depends(caller_tenant)]
