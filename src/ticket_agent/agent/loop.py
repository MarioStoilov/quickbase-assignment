"""The agent loop: one request in, model turns and tool calls until the model is done.

`run_turn` starts from a new user message; `resume_turn` starts from the person's answer
to a tool call the conversation was frozen on. Both then run the same continuation: any
unanswered tool call of the newest model turn is handled, then the model is called
again, until a turn ends without tool calls, a tool needs the person's answer, the
round bound is hit, or the provider fails.

The loop yields its own events rather than the provider's so that the HTTP encoder
never depends on the model layer. Tool calls are handled one at a time in the order the
model made them; a tool that needs the person's answer stops the loop, and the calls
after it wait until the answer arrives.
"""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from ticket_agent.agent.tenant_conversations import TenantConversationStore
from ticket_agent.constants.chat import BLOCKED_TURN_ERROR_TEXT
from ticket_agent.constants.llm import FINISH_REASON_BLOCKED
from ticket_agent.constants.system_prompt import SYSTEM_PROMPT
from ticket_agent.constants.tools import RESULT_ERROR_KEY, TOOL_ROUND_LIMIT_ERROR
from ticket_agent.llm.conversation import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolResultMessage,
)
from ticket_agent.llm.events import TextDelta, ToolCallRequest, TurnFinished
from ticket_agent.llm.provider import ModelProvider, ModelProviderError
from ticket_agent.tickets.repository import TicketRepository
from ticket_agent.tools.base import ToolContext, ToolError
from ticket_agent.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AssistantTextDelta:
    """A fragment of the answer being shown to the person, in order."""

    text: str


@dataclass(frozen=True)
class ToolCallRequested:
    """The model asked for a tool with these arguments; shown in the trace at once."""

    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class ToolCallCompleted:
    """A tool call has a result, whether it ran, failed, or was declined."""

    call_id: str
    result: Mapping[str, Any]


@dataclass(frozen=True)
class ToolResponseRequired:
    """The loop stopped on a call that needs the person to pick one of `options`.

    The conversation is frozen when this is yielded; it is always the last event.
    """

    call_id: str
    tool_name: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class TurnInterrupted:
    """The turn ended without a complete answer; `error_text` is safe to show.

    Any text streamed before the interruption has been kept in the history. Always the
    last event.
    """

    error_text: str


# Everything the loop may yield.
AgentEvent = (
    AssistantTextDelta
    | ToolCallRequested
    | ToolCallCompleted
    | ToolResponseRequired
    | TurnInterrupted
)


@dataclass(frozen=True)
class LoopDependencies:
    """What one run of the loop needs besides the conversation it works on."""

    provider: ModelProvider
    registry: ToolRegistry
    session_factory: sessionmaker[Session]
    max_tool_rounds: int


async def run_turn(
    dependencies: LoopDependencies,
    tenant_id: str,
    conversation_id: str,
    incoming_message: Message,
) -> AsyncIterator[AgentEvent]:
    """Append `incoming_message` to the conversation and drive the loop until it rests.

    The conversation must exist for `tenant_id` and be active (the endpoint checks
    both); the store checks ownership again on every access. The store's calls are
    short SQLite statements and run on the event loop; the session is opened here, not
    taken from the request, because the response outlives the handler.

    Args:
        dependencies: provider, registry, session factory and round bound.
        tenant_id: the caller's tenant, taken from the request, never from a model.
        conversation_id: the conversation the message belongs to.
        incoming_message: what arrived in the request, already validated.

    Yields:
        The loop's events, ending with the model's final text, a
        `ToolResponseRequired`, or a `TurnInterrupted`.

    Raises:
        ConversationNotFound: the conversation is not visible to the tenant.
    """
    with dependencies.session_factory() as session:
        store = TenantConversationStore(session)
        context = _context_for(session, tenant_id, conversation_id)

        store.append(tenant_id, conversation_id, incoming_message)

        async for event in _continue(dependencies, store, context):
            yield event


async def resume_turn(
    dependencies: LoopDependencies,
    tenant_id: str,
    conversation_id: str,
    pending_call: ToolCall,
    response_option: str,
) -> AsyncIterator[AgentEvent]:
    """Resolve the call the conversation is frozen on with the person's answer, then go on.

    The tool runs with the arguments stored when the model made the call; nothing the
    client sent besides the option is used. The endpoint has checked that the call is
    the pending one and that the option is offered. The result is stored and the
    conversation unfrozen before the loop continues, so a provider failure afterwards
    leaves the conversation usable.

    Args:
        dependencies: provider, registry, session factory and round bound.
        tenant_id: the caller's tenant, taken from the request, never from a model.
        conversation_id: the frozen conversation.
        pending_call: the call as stored, from `TenantConversationStore.pending_tool_call`.
        response_option: the option the person picked.

    Yields:
        `ToolCallCompleted` for the resolved call, then the loop's further events.

    Raises:
        ConversationNotFound: the conversation is not visible to the tenant.
    """
    with dependencies.session_factory() as session:
        store = TenantConversationStore(session)
        context = _context_for(session, tenant_id, conversation_id)

        tool = dependencies.registry.get(pending_call.tool_name)
        try:
            result = tool.execute(pending_call.arguments, context, response_option)
        except ToolError as tool_error:
            result = {RESULT_ERROR_KEY: str(tool_error)}

        result_message = ToolResultMessage(
            call_id=pending_call.call_id, tool_name=pending_call.tool_name, result=result
        )
        store.append(tenant_id, conversation_id, result_message)
        store.unfreeze(tenant_id, conversation_id)
        yield ToolCallCompleted(call_id=pending_call.call_id, result=result)

        async for event in _continue(dependencies, store, context):
            yield event


def _context_for(session: Session, tenant_id: str, conversation_id: str) -> ToolContext:
    """Build the context every tool call of this request runs with.

    Args:
        session: the session that lives as long as the stream.
        tenant_id: the caller's tenant.
        conversation_id: the conversation being driven.

    Returns:
        A context whose repository is bound to the same session as the store.
    """
    ticket_repository = TicketRepository(session)
    context = ToolContext(
        tenant_id=tenant_id, conversation_id=conversation_id, ticket_repository=ticket_repository
    )

    return context


async def _continue(
    dependencies: LoopDependencies, store: TenantConversationStore, context: ToolContext
) -> AsyncIterator[AgentEvent]:
    """Handle unanswered tool calls and call the model until the conversation rests.

    Args:
        dependencies: provider, registry, session factory and round bound.
        store: the store bound to the request's session.
        context: the tenant and conversation the tool calls run for.

    Yields:
        The loop's events.
    """
    tenant_id = context.tenant_id
    conversation_id = context.conversation_id
    rounds_used = 0

    while True:
        # Every call of the newest model turn must have a result before the model is
        # called again; the provider requires it, and it is where the person's answer
        # is waited for. Handled one at a time, in the model's order.
        history = store.history(tenant_id, conversation_id)
        unanswered_calls = _unanswered_tool_calls(history)

        for tool_call in unanswered_calls:
            outcome = _run_or_defer(dependencies.registry, tool_call, context)
            is_deferred = outcome is None

            if is_deferred:
                tool = dependencies.registry.get(tool_call.tool_name)
                store.freeze_on_tool_call(tenant_id, conversation_id, tool_call.call_id)
                yield ToolResponseRequired(
                    call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    options=tool.response_options,
                )
                return

            result_message = ToolResultMessage(
                call_id=tool_call.call_id, tool_name=tool_call.tool_name, result=outcome
            )
            store.append(tenant_id, conversation_id, result_message)
            yield ToolCallCompleted(call_id=tool_call.call_id, result=outcome)

        is_bound_hit = rounds_used >= dependencies.max_tool_rounds
        if is_bound_hit:
            yield TurnInterrupted(error_text=TOOL_ROUND_LIMIT_ERROR)
            return

        rounds_used = rounds_used + 1
        history = store.history(tenant_id, conversation_id)
        tool_declarations = dependencies.registry.declarations()

        answer_fragments: list[str] = []
        requested_calls: list[ToolCall] = []
        turn_state: dict[str, Any] = {}
        interruption_text: str | None = None

        # The provider raises for failures it cannot retry; the fragments received
        # until then are kept so the stored history matches the screen.
        try:
            async for event in dependencies.provider.stream_turn(
                SYSTEM_PROMPT, history, tool_declarations
            ):
                if isinstance(event, TextDelta):
                    answer_fragments.append(event.text)
                    yield AssistantTextDelta(text=event.text)
                elif isinstance(event, ToolCallRequest):
                    requested_call = ToolCall(
                        call_id=event.call_id,
                        tool_name=event.tool_name,
                        arguments=event.arguments,
                        provider_state=event.provider_state,
                    )
                    requested_calls.append(requested_call)
                    yield ToolCallRequested(
                        call_id=event.call_id, tool_name=event.tool_name, arguments=event.arguments
                    )
                elif isinstance(event, TurnFinished):
                    turn_state = dict(event.provider_state)
                    is_blocked = event.reason == FINISH_REASON_BLOCKED
                    if is_blocked:
                        interruption_text = f"{BLOCKED_TURN_ERROR_TEXT}: {event.detail}"
        except ModelProviderError as provider_error:
            interruption_text = str(provider_error)

        # An interrupted turn keeps its text but drops its tool calls: none of them was
        # acted on, and a stored call without a result would make the next model
        # request invalid.
        is_interrupted = interruption_text is not None
        if is_interrupted:
            requested_calls = []

        answer_text = "".join(answer_fragments)
        has_content = answer_text != "" or len(requested_calls) > 0
        if has_content:
            assistant_message = AssistantMessage(
                text=answer_text, tool_calls=tuple(requested_calls), provider_state=turn_state
            )
            store.append(tenant_id, conversation_id, assistant_message)

        if is_interrupted:
            yield TurnInterrupted(error_text=interruption_text)
            return

        has_tool_calls = len(requested_calls) > 0
        if not has_tool_calls:
            return


def _unanswered_tool_calls(history: list[Message]) -> list[ToolCall]:
    """Return the calls of the newest assistant message that have no result yet.

    Args:
        history: the conversation so far, oldest first.

    Returns:
        The unanswered calls in the order the model made them; empty when the newest
        assistant message made no calls or all are answered.
    """
    newest_assistant_index: int | None = None
    for index, message in enumerate(history):
        is_assistant = isinstance(message, AssistantMessage)
        if is_assistant:
            newest_assistant_index = index

    has_assistant_message = newest_assistant_index is not None
    if not has_assistant_message:
        return []

    newest_assistant = history[newest_assistant_index]
    messages_after = history[newest_assistant_index + 1 :]

    answered_call_ids = set()
    for message in messages_after:
        is_result = isinstance(message, ToolResultMessage)
        if is_result:
            answered_call_ids.add(message.call_id)

    unanswered_calls = []
    for tool_call in newest_assistant.tool_calls:
        is_answered = tool_call.call_id in answered_call_ids
        if not is_answered:
            unanswered_calls.append(tool_call)

    return unanswered_calls


def _run_or_defer(
    registry: ToolRegistry, tool_call: ToolCall, context: ToolContext
) -> Mapping[str, Any] | None:
    """Validate a call and run it unless its tool needs the person's answer first.

    Validation runs for every tool, so a call that cannot succeed (unknown tool, bad
    arguments, a ticket outside the tenant) gets an error result at once and never
    freezes the conversation.

    Args:
        registry: the tools the model may use.
        tool_call: the call as the model made it.
        context: the tenant and conversation the call runs for.

    Returns:
        The result to hand back to the model, or None when the tool must wait for the
        person's answer.
    """
    try:
        tool = registry.get(tool_call.tool_name)
        tool.validate(tool_call.arguments, context)
    except ToolError as tool_error:
        error_result = {RESULT_ERROR_KEY: str(tool_error)}
        return error_result

    needs_response = len(tool.response_options) > 0
    if needs_response:
        return None

    try:
        result = tool.execute(tool_call.arguments, context, None)
    except ToolError as tool_error:
        error_result = {RESULT_ERROR_KEY: str(tool_error)}
        return error_result

    return result
