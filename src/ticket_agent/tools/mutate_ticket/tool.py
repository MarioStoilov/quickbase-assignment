"""The `mutate_ticket` tool implementation."""

from collections.abc import Mapping
from typing import Any

from ticket_agent.constants.tickets import MUTABLE_TICKET_FIELDS, TICKET_PRIORITIES, TICKET_STATUSES
from ticket_agent.tickets.repository import InvalidTicketFields, TicketNotFound
from ticket_agent.tools.base import Tool, ToolContext, ToolError
from ticket_agent.tools.mutate_ticket.arguments import action_of, ticket_id_of, update_fields_of
from ticket_agent.tools.mutate_ticket.constants import (
    ACTION_ARGUMENT,
    ACTION_UPDATE,
    DETAIL_RESULT_KEY,
    FIELDS_ARGUMENT,
    MUTATE_RESPONSE_OPTIONS,
    MUTATE_TICKET_TOOL_NAME,
    PERFORMED_RESULT_KEY,
    REJECTED_BY_USER_RESULT,
    RESPONSE_OPTION_APPROVE,
    TICKET_ACTIONS,
    TICKET_ID_ARGUMENT,
)


class MutateTicketTool(Tool):
    """Updates or deletes one ticket of the calling tenant, once the person approves.

    Every call freezes the conversation until the person picks approve or reject, so the
    model can never carry out a change on its own, whatever a ticket's text tells it.
    """

    @property
    def name(self) -> str:
        """The name the model calls this tool by."""
        return MUTATE_TICKET_TOOL_NAME

    @property
    def description(self) -> str:
        """What the tool does, as told to the model."""
        return (
            "Propose a change to one ticket of the organisation you work for: update "
            "its fields or delete it. The change is not carried out when you call this "
            "tool; the person is asked first and may decline. Call it once per ticket."
        )

    @property
    def parameters_schema(self) -> Mapping[str, Any]:
        """JSON schema of the arguments the model supplies."""
        allowed_field_names = ", ".join(sorted(MUTABLE_TICKET_FIELDS))
        status_values = ", ".join(TICKET_STATUSES)
        priority_values = ", ".join(TICKET_PRIORITIES)

        schema = {
            "type": "object",
            "properties": {
                TICKET_ID_ARGUMENT: {
                    "type": "integer",
                    "description": "Id of the ticket to change, as returned by search.",
                },
                ACTION_ARGUMENT: {
                    "type": "string",
                    "enum": list(TICKET_ACTIONS),
                    "description": "What to do with the ticket.",
                },
                FIELDS_ARGUMENT: {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        f"For an update, the fields to change. Allowed: "
                        f"{allowed_field_names}. Status must be one of {status_values}; "
                        f"priority one of {priority_values}. Omit for a delete."
                    ),
                },
            },
            "required": [TICKET_ID_ARGUMENT, ACTION_ARGUMENT],
        }

        return schema

    @property
    def response_options(self) -> tuple[str, ...]:
        """A change is carried out only after the person picks approve."""
        return MUTATE_RESPONSE_OPTIONS

    def validate(self, arguments: Mapping[str, Any], context: ToolContext) -> None:
        """Check the arguments and that the ticket belongs to the calling tenant.

        Ownership is checked here, before the person is asked, so a ticket of another
        tenant never produces a prompt: the model is told the ticket does not exist and
        the conversation is not frozen. An update's fields are checked against the
        repository's rules for the same reason.

        Args:
            arguments: what the model supplied.
            context: the tenant and conversation the call runs for.

        Raises:
            ToolError: the arguments are unusable, or the ticket does not exist within
                the caller's tenant.
        """
        ticket_id = ticket_id_of(arguments)
        action = action_of(arguments)
        is_update = action == ACTION_UPDATE

        if is_update:
            fields = update_fields_of(arguments)
            try:
                context.ticket_repository.validate_update_fields(fields)
            except InvalidTicketFields as invalid_fields:
                raise ToolError(str(invalid_fields)) from invalid_fields

        # The tenant check comes last so that a malformed call is reported as malformed,
        # but it never depends on the action: a foreign ticket and a missing one produce
        # the same error for update and delete alike.
        try:
            context.ticket_repository.get(context.tenant_id, ticket_id)
        except TicketNotFound as not_found:
            raise ToolError(str(not_found)) from not_found

    def execute(
        self, arguments: Mapping[str, Any], context: ToolContext, response: str | None
    ) -> Mapping[str, Any]:
        """Carry out the change the person approved, or report that they declined.

        The arguments are the ones stored when the call was made, so a client cannot
        alter what runs by sending different ones with the response. Ownership is
        checked again here, because the ticket may have changed hands or vanished while
        the conversation was frozen.

        Args:
            arguments: the stored arguments of the frozen call.
            context: the tenant and conversation the call runs for.
            response: `approve` or `reject`, as picked by the person.

        Returns:
            What happened, for the model to report.

        Raises:
            ToolError: the ticket is no longer reachable, or the change was refused by
                the repository.
        """
        is_approved = response == RESPONSE_OPTION_APPROVE

        if not is_approved:
            declined_result = {
                PERFORMED_RESULT_KEY: False,
                DETAIL_RESULT_KEY: REJECTED_BY_USER_RESULT,
            }
            return declined_result

        ticket_id = ticket_id_of(arguments)
        action = action_of(arguments)
        is_update = action == ACTION_UPDATE

        try:
            if is_update:
                fields = update_fields_of(arguments)
                ticket = context.ticket_repository.update(context.tenant_id, ticket_id, fields)
                changed_field_names = ", ".join(sorted(fields))
                detail = f"updated {changed_field_names} of ticket {ticket.id}"
            else:
                ticket = context.ticket_repository.delete(context.tenant_id, ticket_id)
                detail = f"deleted ticket {ticket.id}"
        except (TicketNotFound, InvalidTicketFields) as failure:
            raise ToolError(str(failure)) from failure

        result = {
            PERFORMED_RESULT_KEY: True,
            ACTION_ARGUMENT: action,
            TICKET_ID_ARGUMENT: ticket.id,
            DETAIL_RESULT_KEY: detail,
        }

        return result
