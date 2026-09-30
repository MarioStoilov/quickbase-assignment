"""`search_tickets` called directly: scoped to the context's tenant, never asks."""

import pytest
from sqlalchemy.orm import Session

from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID
from ticket_agent.tickets.repository import TicketRepository
from ticket_agent.tools.base import ToolContext
from ticket_agent.tools.search_tickets import SearchTicketsTool


@pytest.fixture
def acme_context(session: Session) -> ToolContext:
    """A context for an Acme conversation."""
    context = ToolContext(
        tenant_id=ACME_TENANT_ID,
        conversation_id="conversation-acme",
        ticket_repository=TicketRepository(session),
    )

    return context


def test_search_has_no_response_options() -> None:
    """Reading changes nothing, so the tool never freezes the conversation."""
    tool = SearchTicketsTool()

    assert tool.response_options == ()


def test_search_returns_only_the_context_tenants_tickets_without_tenant_ids(
    acme_context: ToolContext,
) -> None:
    """Every result row is an Acme ticket and no row exposes a tenant id."""
    tool = SearchTicketsTool()
    tool.validate({"query": ""}, acme_context)

    result = tool.execute({"query": ""}, acme_context, None)

    returned_ids = [ticket["id"] for ticket in result["tickets"]]
    assert returned_ids == [1, 2, 3, 4, 5, 6]
    assert result["count"] == 6
    for ticket in result["tickets"]:
        assert "tenant_id" not in ticket


def test_search_for_a_foreign_ticket_finds_nothing(acme_context: ToolContext) -> None:
    """Text that only Globex's ticket 47 contains yields no result for Acme."""
    tool = SearchTicketsTool()

    result = tool.execute({"query": "merger data room"}, acme_context, None)

    assert result["tickets"] == []
    assert result["count"] == 0


def test_search_ignores_a_missing_query(acme_context: ToolContext) -> None:
    """A call without the argument is read as the empty query and lists everything."""
    tool = SearchTicketsTool()

    result = tool.execute({}, acme_context, None)

    assert result["count"] == 6


def test_search_as_globex_sees_the_target_ticket(session: Session) -> None:
    """The same tool with a Globex context returns ticket 47: scoping is the context's."""
    globex_context = ToolContext(
        tenant_id=GLOBEX_TENANT_ID,
        conversation_id="conversation-globex",
        ticket_repository=TicketRepository(session),
    )
    tool = SearchTicketsTool()

    result = tool.execute({"query": "merger"}, globex_context, None)

    assert [ticket["id"] for ticket in result["tickets"]] == [47]
