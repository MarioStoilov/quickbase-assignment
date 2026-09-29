"""What a tool is: its declaration to the model, its context, and its two methods.

A tool never receives the tenant or the conversation as a model-supplied argument. Those
come from `ToolContext`, which the agent loop builds from the conversation row the
request was authorised against, so no tool call can name a tenant the caller is not.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ticket_agent.llm.conversation import ToolDeclaration
from ticket_agent.tickets.repository import TicketRepository


class ToolError(Exception):
    """A tool call cannot run: bad arguments, or a ticket the caller may not touch.

    The message is handed to the model as the content of a normal tool result, so it is
    written for the model to read and must not reveal anything about other tenants.
    """


@dataclass(frozen=True)
class ToolContext:
    """Who a tool call runs for and what it may touch.

    One instance describes a single conversation of a single tenant. Both values are
    taken from the authorised request, never from the model's arguments; a tool that
    needs either reads it here.
    """

    tenant_id: str
    conversation_id: str
    ticket_repository: TicketRepository


class Tool(ABC):
    """One capability the model may request, with the rules for running it.

    A tool with a non-empty `response_options` cannot run on the model's word alone: the
    loop freezes the conversation and waits for the person to pick one of the options,
    which is then passed to `execute`. A tool with no options runs as soon as its
    arguments validate.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The name the model calls this tool by."""

    @property
    @abstractmethod
    def description(self) -> str:
        """What the tool does, as told to the model."""

    @property
    @abstractmethod
    def parameters_schema(self) -> Mapping[str, Any]:
        """JSON schema of the arguments the model supplies.

        The schema never contains a tenant or conversation field; those come from
        `ToolContext`.
        """

    @property
    @abstractmethod
    def response_options(self) -> tuple[str, ...]:
        """The answers the person may give before this tool runs.

        Empty means the tool runs without asking. Non-empty means every call freezes the
        conversation until one of these values is chosen.
        """

    @abstractmethod
    def validate(self, arguments: Mapping[str, Any], context: ToolContext) -> None:
        """Check the arguments and the caller's right to act on them.

        Runs before anything is executed and, for a tool with response options, before
        the person is asked, so a call that can never succeed never reaches them.

        Args:
            arguments: what the model supplied.
            context: the tenant and conversation the call runs for.

        Raises:
            ToolError: the arguments are unusable or name something the tenant may not
                touch.
        """

    @abstractmethod
    def execute(
        self, arguments: Mapping[str, Any], context: ToolContext, response: str | None
    ) -> Mapping[str, Any]:
        """Run the call and return the result handed back to the model.

        `validate` has already run against the same arguments. For a tool with response
        options, `response` is the option the person picked; for one without, it is None.

        Args:
            arguments: what the model supplied, unchanged since validation.
            context: the tenant and conversation the call runs for.
            response: the chosen option, or None when the tool asks for none.

        Returns:
            A JSON-compatible mapping describing the outcome.

        Raises:
            ToolError: the call could not be completed after all, for example because
                the ticket disappeared between validation and execution.
        """

    def declaration(self) -> ToolDeclaration:
        """Describe this tool to the model.

        Returns:
            The provider-neutral declaration carrying name, description and schema.
        """
        declaration = ToolDeclaration(
            name=self.name,
            description=self.description,
            parameters_schema=self.parameters_schema,
        )

        return declaration
