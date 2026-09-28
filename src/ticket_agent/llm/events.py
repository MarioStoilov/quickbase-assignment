"""Events a provider yields while streaming one model turn."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TextDelta:
    """A fragment of the model's visible answer, in order."""

    text: str


@dataclass(frozen=True)
class ToolCallRequest:
    """The model asks for a tool to be run. Nothing is run by the provider itself.

    `provider_state` must be copied onto the `ToolCall` recorded in the history; see
    `conversation.ToolCall`.
    """

    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    provider_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnFinished:
    """The last event of a turn: why the model stopped.

    `reason` is one of the `FINISH_REASON_*` constants; `detail` carries the provider's
    own wording when the reason is `blocked`, otherwise None. `provider_state` is opaque
    data for the turn as a whole that the caller stores on the `AssistantMessage`.
    """

    reason: str
    detail: str | None = None
    provider_state: Mapping[str, Any] = field(default_factory=dict)


# Everything `ModelProvider.stream_turn` may yield.
ModelEvent = TextDelta | ToolCallRequest | TurnFinished
