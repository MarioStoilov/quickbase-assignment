"""`create_ticket` called directly: rules before the prompt, the caller's tenant after."""

import pytest
from sqlalchemy.orm import Session

from tests.constants.tools import VALID_CREATE_ARGUMENTS
from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID
from ticket_agent.constants.tickets import DEFAULT_TICKET_PRIORITY, DEFAULT_TICKET_STATUS
from ticket_agent.tickets.repository import TicketNotFound, TicketRepository
from ticket_agent.tools.base import ToolContext, ToolError
from ticket_agent.tools.create_ticket import CreateTicketTool


@pytest.fixture
def acme_context(session: Session) -> ToolContext:
    """A context for an Acme conversation."""
    context = ToolContext(
        tenant_id=ACME_TENANT_ID,
        conversation_id="conversation-acme",
        ticket_repository=TicketRepository(session),
    )

    return context


def test_create_offers_approve_and_reject() -> None:
    """Every call must be answered with one of the two options."""
    tool = CreateTicketTool()

    assert tool.response_options == ("approve", "reject")


@pytest.mark.parametrize(
    ("missing_argument", "expected_fragment"),
    [
        ("title", "'title' is required"),
        ("description", "'description' is required"),
        ("requester_email", "'requester_email' is required"),
    ],
)
def test_validate_requires_title_description_and_email(
    acme_context: ToolContext, missing_argument: str, expected_fragment: str
) -> None:
    """Each required argument is named when it is missing."""
    tool = CreateTicketTool()
    arguments = dict(VALID_CREATE_ARGUMENTS)
    del arguments[missing_argument]

    with pytest.raises(ToolError) as failure:
        tool.validate(arguments, acme_context)

    assert expected_fragment in str(failure.value)


def test_validate_applies_the_repository_rules(acme_context: ToolContext) -> None:
    """An unknown priority is refused before the person is asked."""
    tool = CreateTicketTool()
    arguments = {**VALID_CREATE_ARGUMENTS, "priority": "urgent"}

    with pytest.raises(ToolError, match="not a valid priority"):
        tool.validate(arguments, acme_context)


def test_execute_with_reject_creates_nothing(acme_context: ToolContext) -> None:
    """A rejected call returns the declined result and the listing is unchanged."""
    tool = CreateTicketTool()
    count_before = len(acme_context.ticket_repository.list_for_tenant(ACME_TENANT_ID))

    result = tool.execute(VALID_CREATE_ARGUMENTS, acme_context, "reject")

    assert result["performed"] is False
    assert len(acme_context.ticket_repository.list_for_tenant(ACME_TENANT_ID)) == count_before


def test_execute_with_approve_creates_an_open_ticket_in_the_callers_tenant(
    acme_context: ToolContext,
) -> None:
    """The ticket is open, has the default priority, and is invisible to Globex."""
    tool = CreateTicketTool()

    result = tool.execute(VALID_CREATE_ARGUMENTS, acme_context, "approve")

    assert result["performed"] is True
    new_ticket = acme_context.ticket_repository.get(ACME_TENANT_ID, result["ticket_id"])
    assert new_ticket.status == DEFAULT_TICKET_STATUS
    assert new_ticket.priority == DEFAULT_TICKET_PRIORITY
    with pytest.raises(TicketNotFound):
        acme_context.ticket_repository.get(GLOBEX_TENANT_ID, result["ticket_id"])


def test_a_tenant_in_the_arguments_is_ignored(acme_context: ToolContext) -> None:
    """A model-supplied tenant field cannot move the ticket to another tenant."""
    tool = CreateTicketTool()
    arguments = {**VALID_CREATE_ARGUMENTS, "tenant_id": GLOBEX_TENANT_ID}

    result = tool.execute(arguments, acme_context, "approve")

    new_ticket = acme_context.ticket_repository.get(ACME_TENANT_ID, result["ticket_id"])
    assert new_ticket.tenant_id == ACME_TENANT_ID
