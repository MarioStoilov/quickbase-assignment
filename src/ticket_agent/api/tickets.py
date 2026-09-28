"""Read-only listing of the caller's tickets, for inspecting the tenant scoping directly."""

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from ticket_agent.auth import CallerTenant
from ticket_agent.db.models import Ticket
from ticket_agent.db.session import DatabaseSession
from ticket_agent.tickets.repository import TicketRepository

router = APIRouter()


class TicketResponse(BaseModel):
    """One ticket as returned to the caller."""

    id: int
    tenant_id: str
    title: str
    description: str
    status: str
    priority: str
    requester_email: str
    created_at: datetime
    updated_at: datetime


def ticket_response_from_model(ticket: Ticket) -> TicketResponse:
    """Copy a ticket row into its response shape.

    Args:
        ticket: the ORM row.

    Returns:
        The response body for that ticket.
    """
    ticket_response = TicketResponse(
        id=ticket.id,
        tenant_id=ticket.tenant_id,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        priority=ticket.priority,
        requester_email=ticket.requester_email,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )

    return ticket_response


@router.get("/api/tickets")
def list_tickets(tenant: CallerTenant, session: DatabaseSession) -> list[TicketResponse]:
    """Return every ticket of the calling tenant.

    Args:
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session.

    Returns:
        The caller's tickets, oldest first.
    """
    ticket_repository = TicketRepository(session)
    tickets = ticket_repository.list_for_tenant(tenant.id)

    ticket_responses = []
    for ticket in tickets:
        ticket_response = ticket_response_from_model(ticket)
        ticket_responses.append(ticket_response)

    return ticket_responses
