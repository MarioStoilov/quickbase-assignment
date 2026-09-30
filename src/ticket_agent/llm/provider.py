"""The interface every model adapter implements."""

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from ticket_agent.llm.conversation import Message, ToolDeclaration
from ticket_agent.llm.events import ModelEvent


class ModelProviderError(Exception):
    """The provider could not complete a turn (network, quota, invalid request).

    The message is safe to show to the person in the chat; it names the failure without
    including request contents.
    """


class ModelProvider(Protocol):
    """One model behind a streaming, tool-aware turn interface.

    Implementations never execute tools; they only report that the model asked for one.
    """

    def stream_turn(
        self,
        system_prompt: str,
        history: Sequence[Message],
        tool_declarations: Sequence[ToolDeclaration],
    ) -> AsyncIterator[ModelEvent]:
        """Send the history to the model and stream its next turn.

        Yields `TextDelta` and `ToolCallRequest` events in the order the model produces
        them and exactly one `TurnFinished` last. A turn that requested tools finishes
        with reason `tool_calls`; the caller runs them, appends `ToolResultMessage`s and
        calls again.

        Args:
            system_prompt: instructions sent ahead of the history on every call.
            history: the conversation so far, oldest first.
            tool_declarations: tools the model may request; empty for a plain chat.

        Raises:
            ModelProviderError: the provider rejected or failed the request.
        """
        ...

    async def aclose(self) -> None:
        """Release whatever the provider holds open, such as HTTP connections.

        Called once at application shutdown. A provider that holds nothing does nothing.
        """
        ...
