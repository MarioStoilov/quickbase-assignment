"""One turn of the agent: store the incoming message, stream the model, store the answer.

No tools are declared yet, so a turn is a single model call. The loop yields its own
events rather than the provider's so that the HTTP encoder never depends on the model
layer, and so that later tool and approval events slot in beside the text ones.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ticket_agent.agent.tenant_conversations import TenantConversationStore
from ticket_agent.constants.chat import BLOCKED_TURN_ERROR_TEXT
from ticket_agent.constants.llm import FINISH_REASON_BLOCKED
from ticket_agent.constants.system_prompt import SYSTEM_PROMPT
from ticket_agent.llm.conversation import AssistantMessage, Message
from ticket_agent.llm.events import TextDelta, TurnFinished
from ticket_agent.llm.provider import ModelProvider, ModelProviderError


@dataclass(frozen=True)
class AssistantTextDelta:
    """A fragment of the answer being shown to the person, in order."""

    text: str


@dataclass(frozen=True)
class TurnInterrupted:
    """The turn ended without a complete answer; `error_text` is safe to show.

    Any text streamed before the interruption has been kept in the history.
    """

    error_text: str


# Everything `run_turn` may yield.
AgentEvent = AssistantTextDelta | TurnInterrupted


async def run_turn(
    provider: ModelProvider,
    session_factory: sessionmaker[Session],
    tenant_id: str,
    conversation_id: str,
    incoming_message: Message,
) -> AsyncIterator[AgentEvent]:
    """Append `incoming_message` to the conversation and stream the model's reply.

    The conversation must already be visible to `tenant_id` (see
    `TenantConversationStore.get_or_create`); the store checks that again on every
    access. The reply is stored as one assistant message when the model finishes. A
    provider failure or a blocked answer yields `TurnInterrupted` last; text received
    before that point is stored, so the history stays consistent with what the person
    saw. A turn with no text at all stores no assistant message.

    The store's calls are short SQLite statements and run on the event loop; the
    session is opened here, not taken from the request, because the response outlives
    the handler.

    Args:
        provider: the model to talk to.
        session_factory: opens the session that lives as long as the stream.
        tenant_id: the caller's tenant, taken from the request, never from a model.
        conversation_id: the conversation the message belongs to.
        incoming_message: what arrived in the request, already validated.

    Yields:
        `AssistantTextDelta` per fragment, then optionally one `TurnInterrupted`.

    Raises:
        ConversationNotFound: the conversation is not visible to the tenant.
    """
    with session_factory() as session:
        store = TenantConversationStore(session)
        store.append(tenant_id, conversation_id, incoming_message)
        history = store.history(tenant_id, conversation_id)

        answer_fragments: list[str] = []
        turn_state: dict[str, Any] = {}
        interruption_text: str | None = None

        # The provider raises for failures it cannot retry; the fragments received
        # until then are kept so the stored history matches the screen.
        try:
            async for event in provider.stream_turn(SYSTEM_PROMPT, history, tool_declarations=[]):
                if isinstance(event, TextDelta):
                    answer_fragments.append(event.text)
                    yield AssistantTextDelta(text=event.text)
                elif isinstance(event, TurnFinished):
                    turn_state = dict(event.provider_state)
                    is_blocked = event.reason == FINISH_REASON_BLOCKED
                    if is_blocked:
                        interruption_text = f"{BLOCKED_TURN_ERROR_TEXT}: {event.detail}"
        except ModelProviderError as provider_error:
            interruption_text = str(provider_error)

        answer_text = "".join(answer_fragments)
        has_answer = answer_text != ""
        if has_answer:
            assistant_message = AssistantMessage(text=answer_text, provider_state=turn_state)
            store.append(tenant_id, conversation_id, assistant_message)

        is_interrupted = interruption_text is not None
        if is_interrupted:
            yield TurnInterrupted(error_text=interruption_text)
