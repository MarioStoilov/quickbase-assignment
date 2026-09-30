"""A `ModelProvider` that replays scripted turns instead of calling a model.

Each scripted turn is the list of events one model call yields. The provider records
every call it receives (system prompt, history, declarations) so a test can assert what
the model was shown, for example that a tool result came back with its provider state.
A turn may also be an exception, raised when that call is made, or an exception placed
among the events, raised once the events before it have been yielded, to stand in for
a provider failure before or during the stream.
"""

from collections import deque
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from tests.constants.provider import OUT_OF_TURNS_MESSAGE
from ticket_agent.llm.conversation import Message, ToolDeclaration
from ticket_agent.llm.events import ModelEvent
from ticket_agent.llm.provider import ModelProviderError

# One scripted model call: the events to yield, with an exception among them raised at
# that point, or the error to raise instead of streaming anything.
ScriptedTurn = Sequence[ModelEvent | Exception] | Exception


@dataclass(frozen=True)
class RecordedCall:
    """What one model call received."""

    system_prompt: str
    history: tuple[Message, ...]
    tool_declarations: tuple[ToolDeclaration, ...]


@dataclass
class ScriptedProvider:
    """Replays `turns` in order, one per `stream_turn` call, recording each call."""

    turns: deque[ScriptedTurn] = field(default_factory=deque)
    calls: list[RecordedCall] = field(default_factory=list)

    def add_turn(self, turn: ScriptedTurn) -> None:
        """Queue one more model call's outcome.

        Args:
            turn: the events to yield, or the exception to raise, on that call.
        """
        self.turns.append(turn)

    async def stream_turn(
        self,
        system_prompt: str,
        history: Sequence[Message],
        tool_declarations: Sequence[ToolDeclaration],
    ) -> AsyncIterator[ModelEvent]:
        """Record the call and replay the next scripted turn.

        Args:
            system_prompt: what the loop sends as instructions.
            history: the conversation the loop sends.
            tool_declarations: the tools the loop offers.

        Yields:
            The scripted events, in order.

        Raises:
            ModelProviderError: no turn is left, the scripted turn is an error, or an
                error was scripted among the events.
        """
        recorded_call = RecordedCall(
            system_prompt=system_prompt,
            history=tuple(history),
            tool_declarations=tuple(tool_declarations),
        )
        self.calls.append(recorded_call)

        has_turn = len(self.turns) > 0
        if not has_turn:
            raise ModelProviderError(OUT_OF_TURNS_MESSAGE)

        turn = self.turns.popleft()
        is_failure = isinstance(turn, Exception)
        if is_failure:
            raise turn

        for event in turn:
            is_mid_stream_failure = isinstance(event, Exception)
            if is_mid_stream_failure:
                raise event
            yield event
