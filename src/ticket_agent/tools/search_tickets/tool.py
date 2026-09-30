"""The `search_tickets` tool implementation."""

from collections.abc import Mapping
from typing import Any

from ticket_agent.constants.tickets import SEARCH_RESULT_LIMIT
from ticket_agent.db.models import Ticket
from ticket_agent.tickets.repository import TicketNotFound
from ticket_agent.tools.base import Tool, ToolContext
from ticket_agent.tools.search_tickets.arguments import query_of, ticket_id_of
from ticket_agent.tools.search_tickets.constants import (
    COUNT_RESULT_KEY,
    QUERY_ARGUMENT,
    SEARCH_TICKETS_TOOL_NAME,
    TICKET_ID_ARGUMENT,
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
    """Finds tickets of the calling tenant by text or by id; runs without asking the person.

    Both ways are scoped the same: the tenant comes from the context, so a lookup by
    an id that belongs to another tenant finds nothing, exactly like a missing id.
    """

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
            f"them. Returns at most {SEARCH_RESULT_LIMIT} tickets. To look one ticket up "
            f"by its number, pass {TICKET_ID_ARGUMENT} instead of a query; a ticket that "
            "does not exist gives an empty result."
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
                },
                TICKET_ID_ARGUMENT: {
                    "type": "integer",
                    "description": (
                        "Number of one ticket to fetch, for example 2 for #2. When given, "
                        "the query is ignored."
                    ),
                },
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

        Raises:
            ToolError: a ticket id is given but is not a whole number.
        """
        ticket_id_of(arguments)

    def execute(
        self, arguments: Mapping[str, Any], context: ToolContext, response: str | None
    ) -> Mapping[str, Any]:
        """Search within the caller's tenant, or fetch one ticket of it, and return the matches.

        The tenant id comes from `context`, never from `arguments`, so neither the query
        nor the id can reach beyond the caller's own tickets. A lookup by an id that is
        missing or belongs to another tenant returns an empty result, not an error, so
        the model cannot tell the two apart.

        Args:
            arguments: may hold `query` and `ticket_id`; anything else is ignored.
            context: the tenant and conversation the call runs for.
            response: always None; this tool asks for no response.

        Returns:
            The matching tickets and how many were returned.
        """
        ticket_id = ticket_id_of(arguments)
        is_lookup_by_id = ticket_id is not None

        if is_lookup_by_id:
            try:
                ticket = context.ticket_repository.get(context.tenant_id, ticket_id)
                tickets = [ticket]
            except TicketNotFound:
                tickets = []
        else:
            query = query_of(arguments)
            tickets = context.ticket_repository.search(context.tenant_id, query)

        ticket_summaries = []
        for ticket in tickets:
            summary = ticket_summary(ticket)
            ticket_summaries.append(summary)

        result = {TICKETS_RESULT_KEY: ticket_summaries, COUNT_RESULT_KEY: len(ticket_summaries)}

        return result
