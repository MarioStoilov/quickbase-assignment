"""`mutate_ticket` called directly: validation before the prompt, frozen arguments after."""

import pytest
from sqlalchemy.orm import Session

from ticket_agent.constants.seed import ACME_TENANT_ID, TARGET_FOREIGN_TICKET_ID
from ticket_agent.tickets.repository import TicketNotFound, TicketRepository
from ticket_agent.tools.base import ToolContext, ToolError
from ticket_agent.tools.mutate_ticket import MutateTicketTool


@pytest.fixture
def acme_context(session: Session) -> ToolContext:
    """A context for an Acme conversation."""
    context = ToolContext(
        tenant_id=ACME_TENANT_ID,
        conversation_id="conversation-acme",
        ticket_repository=TicketRepository(session),
    )

    return context


def test_mutate_offers_approve_and_reject() -> None:
    """Every call must be answered with one of the two options."""
    tool = MutateTicketTool()

    assert tool.response_options == ("approve", "reject")


@pytest.mark.parametrize(
    ("arguments", "expected_fragment"),
    [
        ({"action": "delete"}, "'ticket_id' is required"),
        ({"ticket_id": "abc", "action": "delete"}, "whole number"),
        ({"ticket_id": 1, "action": "archive"}, "must be one of"),
        ({"ticket_id": 1, "action": "update"}, "'fields' is required"),
        ({"ticket_id": 1, "action": "update", "fields": {}}, "at least one field"),
        ({"ticket_id": 1, "action": "update", "fields": {"status": "done"}}, "not a valid status"),
    ],
)
def test_validate_rejects_malformed_calls_before_any_lookup(
    acme_context: ToolContext, arguments: dict, expected_fragment: str
) -> None:
    """Missing or bad arguments are reported to the model with a usable message."""
    tool = MutateTicketTool()

    with pytest.raises(ToolError) as failure:
        tool.validate(arguments, acme_context)

    assert expected_fragment in str(failure.value)


def test_validate_reports_a_foreign_ticket_as_not_found(acme_context: ToolContext) -> None:
    """Globex's ticket 47 fails validation for Acme like a missing id would."""
    tool = MutateTicketTool()

    with pytest.raises(ToolError, match=f"ticket {TARGET_FOREIGN_TICKET_ID} not found"):
        tool.validate({"ticket_id": TARGET_FOREIGN_TICKET_ID, "action": "delete"}, acme_context)


def test_validate_accepts_an_own_ticket(acme_context: ToolContext) -> None:
    """A well-formed call on an Acme ticket passes validation."""
    tool = MutateTicketTool()

    tool.validate(
        {"ticket_id": 4, "action": "update", "fields": {"priority": "high"}}, acme_context
    )


def test_execute_with_reject_changes_nothing(acme_context: ToolContext) -> None:
    """A rejected call returns the declined result and the ticket keeps its values."""
    tool = MutateTicketTool()
    arguments = {"ticket_id": 4, "action": "delete"}

    result = tool.execute(arguments, acme_context, "reject")

    assert result["performed"] is False
    assert acme_context.ticket_repository.get(ACME_TENANT_ID, 4).title.startswith("Dashboard")


def test_execute_with_approve_applies_the_update(acme_context: ToolContext) -> None:
    """An approved update writes the fields and reports what changed."""
    tool = MutateTicketTool()
    arguments = {"ticket_id": 4, "action": "update", "fields": {"status": "closed"}}

    result = tool.execute(arguments, acme_context, "approve")

    assert result["performed"] is True
    assert result["ticket_id"] == 4
    assert "status" in result["detail"]
    assert acme_context.ticket_repository.get(ACME_TENANT_ID, 4).status == "closed"


def test_execute_with_approve_deletes_the_ticket(acme_context: ToolContext) -> None:
    """An approved delete removes the ticket."""
    tool = MutateTicketTool()

    result = tool.execute({"ticket_id": 6, "action": "delete"}, acme_context, "approve")

    assert result["performed"] is True
    with pytest.raises(TicketNotFound):
        acme_context.ticket_repository.get(ACME_TENANT_ID, 6)


def test_execute_rechecks_ownership_for_a_foreign_ticket(acme_context: ToolContext) -> None:
    """Even an approved call on Globex's ticket fails: ownership is checked at execution too."""
    tool = MutateTicketTool()

    with pytest.raises(ToolError, match="not found"):
        tool.execute(
            {"ticket_id": TARGET_FOREIGN_TICKET_ID, "action": "delete"}, acme_context, "approve"
        )
