"""Readers for the model-supplied arguments of `mutate_ticket`.

Each reader turns a loosely typed argument into the value the tool works with, or
raises `ToolError` with a message the model can act on.
"""

from collections.abc import Mapping
from typing import Any

from ticket_agent.tools.base import ToolError
from ticket_agent.tools.mutate_ticket.constants import (
    ACTION_ARGUMENT,
    FIELDS_ARGUMENT,
    TICKET_ACTIONS,
    TICKET_ID_ARGUMENT,
)


def ticket_id_of(arguments: Mapping[str, Any]) -> int:
    """Read the ticket id as an integer.

    Args:
        arguments: what the model supplied; the id may arrive as a number or a string.

    Returns:
        The ticket id.

    Raises:
        ToolError: the argument is missing or is not a whole number.
    """
    raw_ticket_id = arguments.get(TICKET_ID_ARGUMENT)
    is_present = raw_ticket_id is not None

    if not is_present:
        raise ToolError(f"'{TICKET_ID_ARGUMENT}' is required")

    try:
        ticket_id = int(raw_ticket_id)
    except (TypeError, ValueError) as conversion_error:
        raise ToolError(f"'{TICKET_ID_ARGUMENT}' must be a whole number") from conversion_error

    return ticket_id


def action_of(arguments: Mapping[str, Any]) -> str:
    """Read the action.

    Args:
        arguments: what the model supplied.

    Returns:
        The action, one of `TICKET_ACTIONS`.

    Raises:
        ToolError: the argument is missing or names an unknown action.
    """
    raw_action = arguments.get(ACTION_ARGUMENT)
    action = str(raw_action) if raw_action is not None else ""
    is_known_action = action in TICKET_ACTIONS

    if not is_known_action:
        allowed_actions = ", ".join(TICKET_ACTIONS)
        raise ToolError(f"'{ACTION_ARGUMENT}' must be one of: {allowed_actions}")

    return action


def update_fields_of(arguments: Mapping[str, Any]) -> dict[str, str]:
    """Read the fields of an update.

    Args:
        arguments: what the model supplied.

    Returns:
        The column-to-value mapping, with values as strings.

    Raises:
        ToolError: the argument is missing, is not an object, or is empty.
    """
    raw_fields = arguments.get(FIELDS_ARGUMENT)
    is_mapping = isinstance(raw_fields, Mapping)

    if not is_mapping:
        raise ToolError(f"'{FIELDS_ARGUMENT}' is required for an update and must be an object")

    fields = {}
    for field_name, new_value in raw_fields.items():
        fields[str(field_name)] = str(new_value)

    is_empty = len(fields) == 0
    if is_empty:
        raise ToolError(f"'{FIELDS_ARGUMENT}' must name at least one field to change")

    return fields
