"""Readers for the model-supplied arguments of `search_tickets`.

Each reader turns a loosely typed argument into the value the tool works with, or
raises `ToolError` with a message the model can act on.
"""

from collections.abc import Mapping
from typing import Any

from ticket_agent.tools.base import ToolError
from ticket_agent.tools.search_tickets.constants import QUERY_ARGUMENT, TICKET_ID_ARGUMENT


def query_of(arguments: Mapping[str, Any]) -> str:
    """Read the free-text query; a missing one is the empty query.

    Args:
        arguments: what the model supplied.

    Returns:
        The query as a string, possibly empty.
    """
    raw_query = arguments.get(QUERY_ARGUMENT, "")
    query = str(raw_query)

    return query


def ticket_id_of(arguments: Mapping[str, Any]) -> int | None:
    """Read the optional ticket id as an integer.

    Args:
        arguments: what the model supplied; the id may arrive as a number or a string.

    Returns:
        The ticket id, or None when the argument is absent.

    Raises:
        ToolError: the argument is present but is not a whole number.
    """
    raw_ticket_id = arguments.get(TICKET_ID_ARGUMENT)
    is_absent = raw_ticket_id is None
    if is_absent:
        return None

    try:
        ticket_id = int(raw_ticket_id)
    except (TypeError, ValueError) as conversion_error:
        raise ToolError(f"'{TICKET_ID_ARGUMENT}' must be a whole number") from conversion_error

    return ticket_id
