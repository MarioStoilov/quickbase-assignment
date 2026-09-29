"""The `search_tickets` tool implementation."""

from collections.abc import Mapping
from typing import Any

from ticket_agent.constants.tickets import SEARCH_RESULT_LIMIT
from ticket_agent.db.models import Ticket
from ticket_agent.tools.base import Tool, ToolContext
from ticket_agent.tools.search_tickets.constants import (
    COUNT_RESULT_KEY,
    QUERY_ARGUMENT,
    SEARCH_TICKETS_TOOL_NAME,
    TICKETS_RESULT_KEY,
)


def ticket_summary(ticket: Ticket) -> dict[str, Any]:
    """Describe one ticket for the model.

    The description is included because the person often asks about its content; it is
    end-user text and may carry injected instructions, which the model is told to treat
    as data.

    Args:
        ticket: a ticket row of the caller's tenant.

    Returns:
        The ticket's readable fields. The tenant id is deliberately absent: the model
        never needs it and must not learn tenant identities from a tool result.
    """
    summary = {
        "id": ticket.id,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status,
        "priority": ticket.priority,
        "requester_email": ticket.requester_email,
    }

    return summary


class SearchTicketsTool(Tool):
    """Finds tickets of the calling tenant; runs without asking the person."""

    @property
    def name(self) -> str:
        """The name the model calls this tool by."""
        return SEARCH_TICKETS_TOOL_NAME

    @property
    def description(self) -> str:
        """What the tool does, as told to the model."""
        return (
            "Search the tickets of the organisation you work for. Matches the query "
            "against ticket titles and descriptions; an empty query returns all of "
            f"them. Returns at most {SEARCH_RESULT_LIMIT} tickets."
        )

    @property
    def parameters_schema(self) -> Mapping[str, Any]:
        """JSON schema of the arguments the model supplies."""
        schema = {
            "type": "object",
            "properties": {
                QUERY_ARGUMENT: {
                    "type": "string",
                    "description": (
                        "Words to look for in ticket titles and descriptions. Pass an "
                        "empty string to list every ticket."
                    ),
                }
            },
            "required": [QUERY_ARGUMENT],
        }

        return schema

    @property
    def response_options(self) -> tuple[str, ...]:
        """Reading tickets changes nothing, so the person is never asked."""
        return ()

    def validate(self, arguments: Mapping[str, Any], context: ToolContext) -> None:
        """Accept any query; a missing one is read as the empty query.

        Args:
            arguments: what the model supplied.
            context: the tenant and conversation the call runs for.
        """

    def execute(
        self, arguments: Mapping[str, Any], context: ToolContext, response: str | None
    ) -> Mapping[str, Any]:
        """Search within the caller's tenant and return the matches.

        The tenant id comes from `context`, never from `arguments`, so the query cannot
        widen the search beyond the caller's own tickets.

        Args:
            arguments: may hold `query`; anything else is ignored.
            context: the tenant and conversation the call runs for.
            response: always None; this tool asks for no response.

        Returns:
            The matching tickets and how many were returned.
        """
        raw_query = arguments.get(QUERY_ARGUMENT, "")
        query = str(raw_query)

        tickets = context.ticket_repository.search(context.tenant_id, query)

        ticket_summaries = []
        for ticket in tickets:
            summary = ticket_summary(ticket)
            ticket_summaries.append(summary)

        result = {TICKETS_RESULT_KEY: ticket_summaries, COUNT_RESULT_KEY: len(ticket_summaries)}

        return result
