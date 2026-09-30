"""The `create_ticket` tool implementation."""

from collections.abc import Mapping
from typing import Any

from ticket_agent.constants.tickets import DEFAULT_TICKET_PRIORITY, TICKET_PRIORITIES
from ticket_agent.tickets.repository import InvalidTicketFields
from ticket_agent.tools.base import Tool, ToolContext, ToolError
from ticket_agent.tools.create_ticket.arguments import new_ticket_fields_of
from ticket_agent.tools.create_ticket.constants import (
    CREATE_RESPONSE_OPTIONS,
    CREATE_TICKET_TOOL_NAME,
    DESCRIPTION_ARGUMENT,
    DETAIL_RESULT_KEY,
    PERFORMED_RESULT_KEY,
    PRIORITY_ARGUMENT,
    REJECTED_BY_USER_RESULT,
    REQUESTER_EMAIL_ARGUMENT,
    RESPONSE_OPTION_APPROVE,
    TICKET_ID_RESULT_KEY,
    TITLE_ARGUMENT,
)


class CreateTicketTool(Tool):
    """Creates one ticket in the calling tenant, once the person approves.

    Every call freezes the conversation until the person picks approve or reject, so a
    ticket is never created on the model's word alone, whatever another ticket's text
    tells it. The tenant is never an argument: a ticket lands in the caller's tenant
    and nowhere else.
    """

    @property
    def name(self) -> str:
        """The name the model calls this tool by."""
        return CREATE_TICKET_TOOL_NAME

    @property
    def description(self) -> str:
        """What the tool does, as told to the model."""
        return (
            "Propose a new ticket for the organisation you work for. The ticket is not "
            "created when you call this tool; the person is asked first and may decline. "
            "The requester's e-mail address is required: ask the person for it when they "
            "have not given one. New tickets start open."
        )

    @property
    def parameters_schema(self) -> Mapping[str, Any]:
        """JSON schema of the arguments the model supplies."""
        priority_values = ", ".join(TICKET_PRIORITIES)

        schema = {
            "type": "object",
            "properties": {
                TITLE_ARGUMENT: {
                    "type": "string",
                    "description": "Short title of the new ticket.",
                },
                DESCRIPTION_ARGUMENT: {
                    "type": "string",
                    "description": "What the ticket is about, as the person described it.",
                },
                PRIORITY_ARGUMENT: {
                    "type": "string",
                    "enum": list(TICKET_PRIORITIES),
                    "description": (
                        f"One of {priority_values}. Omit to use {DEFAULT_TICKET_PRIORITY}."
                    ),
                },
                REQUESTER_EMAIL_ARGUMENT: {
                    "type": "string",
                    "description": "E-mail address of the person the ticket is for.",
                },
            },
            "required": [TITLE_ARGUMENT, DESCRIPTION_ARGUMENT, REQUESTER_EMAIL_ARGUMENT],
        }

        return schema

    @property
    def response_options(self) -> tuple[str, ...]:
        """A ticket is created only after the person picks approve."""
        return CREATE_RESPONSE_OPTIONS

    def validate(self, arguments: Mapping[str, Any], context: ToolContext) -> None:
        """Check the fields before the person is asked.

        The repository's rules run here so that a malformed proposal (empty title,
        unknown priority, no address) is reported to the model at once and never
        freezes the conversation.

        Args:
            arguments: what the model supplied.
            context: the tenant and conversation the call runs for.

        Raises:
            ToolError: an argument is missing or breaks the repository's rules.
        """
        fields = new_ticket_fields_of(arguments)

        try:
            context.ticket_repository.validate_new_ticket(
                fields.title, fields.description, fields.priority, fields.requester_email
            )
        except InvalidTicketFields as invalid_fields:
            raise ToolError(str(invalid_fields)) from invalid_fields

    def execute(
        self, arguments: Mapping[str, Any], context: ToolContext, response: str | None
    ) -> Mapping[str, Any]:
        """Create the ticket the person approved, or report that they declined.

        The arguments are the ones stored when the call was made, so a client cannot
        alter what is created by sending different ones with the response. The tenant
        is the context's, so the ticket is created for the caller and nobody else.

        Args:
            arguments: the stored arguments of the frozen call.
            context: the tenant and conversation the call runs for.
            response: `approve` or `reject`, as picked by the person.

        Returns:
            What happened, for the model to report; on success the new ticket's id.

        Raises:
            ToolError: the repository refused the fields.
        """
        is_approved = response == RESPONSE_OPTION_APPROVE

        if not is_approved:
            declined_result = {
                PERFORMED_RESULT_KEY: False,
                DETAIL_RESULT_KEY: REJECTED_BY_USER_RESULT,
            }
            return declined_result

        fields = new_ticket_fields_of(arguments)

        try:
            ticket = context.ticket_repository.create(
                context.tenant_id,
                fields.title,
                fields.description,
                fields.priority,
                fields.requester_email,
            )
        except InvalidTicketFields as invalid_fields:
            raise ToolError(str(invalid_fields)) from invalid_fields

        detail = f"created ticket {ticket.id} with priority {ticket.priority}"
        result = {
            PERFORMED_RESULT_KEY: True,
            TICKET_ID_RESULT_KEY: ticket.id,
            DETAIL_RESULT_KEY: detail,
        }

        return result
