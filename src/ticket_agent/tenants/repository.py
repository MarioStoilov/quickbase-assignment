"""Read access to the tenants table."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticket_agent.db.models import Tenant


class TenantRepository:
    """Queries over the tenants table for one session."""

    def __init__(self, session: Session) -> None:
        """Bind the repository to `session`; the caller owns the session's lifetime."""
        self._session = session

    def get(self, tenant_id: str) -> Tenant | None:
        """Return the tenant with `tenant_id`, or None when there is none.

        Args:
            tenant_id: the slug carried by the `X-Tenant-ID` header.

        Returns:
            The matching `Tenant`, or None.
        """
        tenant = self._session.get(Tenant, tenant_id)

        return tenant

    def list_all(self) -> list[Tenant]:
        """Return every tenant, ordered by display name.

        Returns:
            All tenants; empty when the table is empty.
        """
        statement = select(Tenant).order_by(Tenant.display_name)
        tenants = list(self._session.scalars(statement))

        return tenants
