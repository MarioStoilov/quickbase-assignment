"""Readers for the model-supplied arguments of `create_ticket`.

Each reader turns a loosely typed argument into the value the tool works with, or
raises `ToolError` with a message the model can act on. Content rules (empty, too
long, allowed values) are the repository's; these readers only settle presence and type.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ticket_agent.constants.tickets import DEFAULT_TICKET_PRIORITY
from ticket_agent.tools.base import ToolError
from ticket_agent.tools.create_ticket.constants import (
    DESCRIPTION_ARGUMENT,
    PRIORITY_ARGUMENT,
    REQUESTER_EMAIL_ARGUMENT,
    TITLE_ARGUMENT,
)


@dataclass(frozen=True)
class NewTicketFields:
    """The fields of the ticket the model proposes, as strings."""

    title: str
    description: str
    priority: str
    requester_email: str


def required_text_of(arguments: Mapping[str, Any], argument_name: str) -> str:
    """Read a required argument as text.

    Args:
        arguments: what the model supplied.
        argument_name: the key to read.

    Returns:
        The value as a string.

    Raises:
        ToolError: the argument is missing.
    """
    raw_value = arguments.get(argument_name)
    is_present = raw_value is not None

    if not is_present:
        raise ToolError(f"'{argument_name}' is required")

    text = str(raw_value)

    return text


def new_ticket_fields_of(arguments: Mapping[str, Any]) -> NewTicketFields:
    """Read the fields of the ticket to create.

    Args:
        arguments: what the model supplied.

    Returns:
        The fields, with the default priority filled in when none was given.

    Raises:
        ToolError: the title, description or requester e-mail is missing.
    """
    title = required_text_of(arguments, TITLE_ARGUMENT)
    description = required_text_of(arguments, DESCRIPTION_ARGUMENT)
    requester_email = required_text_of(arguments, REQUESTER_EMAIL_ARGUMENT)

    raw_priority = arguments.get(PRIORITY_ARGUMENT)
    is_priority_given = raw_priority is not None
    priority = str(raw_priority) if is_priority_given else DEFAULT_TICKET_PRIORITY

    fields = NewTicketFields(
        title=title, description=description, priority=priority, requester_email=requester_email
    )

    return fields
