"""Provider-neutral history and tool declarations sent to a model."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation the model asked for, as recorded in the history.

    `provider_state` is opaque, JSON-compatible data the adapter attached when the call
    was streamed and needs back unchanged when the history is resent (for Gemini, the
    thought signature). Empty for providers that need nothing.
    """

    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    provider_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UserMessage:
    """Text typed by the person in the chat."""

    text: str


@dataclass(frozen=True)
class AssistantMessage:
    """One model turn: its visible text and the tool calls it requested, if any.

    `provider_state` is the opaque data `TurnFinished` carried for the turn as a whole,
    stored so the adapter can resend it with the text.
    """

    text: str = ""
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    provider_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResultMessage:
    """The outcome of one tool call, handed back to the model.

    `result` is a JSON-compatible mapping; an error is reported inside it, as a normal
    result the model can read, never as an exception.
    """

    call_id: str
    tool_name: str
    result: Mapping[str, Any]


# Everything a history may contain, in the order it happened.
Message = UserMessage | AssistantMessage | ToolResultMessage


@dataclass(frozen=True)
class ToolDeclaration:
    """What the model is told about one tool: its name, purpose and argument schema."""

    name: str
    description: str
    # JSON schema (draft 2020-12 subset the provider accepts) of the arguments object.
    parameters_schema: Mapping[str, Any]
