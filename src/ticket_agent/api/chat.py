"""The chat endpoints: create a conversation, read it, post to it, answer a tool call.

Lifecycle: `POST /api/chat/new` creates a conversation for the calling tenant and
returns its id; `GET /api/chat/{id}` returns it with its messages and, when frozen, the
tool call it waits on; `POST /api/chat/{id}` appends one user message and streams the
agent's reply; `POST /api/chat/{id}/tool-calls/{call_id}/response` answers the pending
call and streams the continuation. Reads and posts answer 404 for an id that does not
exist or belongs to another tenant, identically.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from ticket_agent.agent.loop import LoopDependencies, resume_turn, run_turn
from ticket_agent.agent.tenant_conversations import (
    ConversationNotFound,
    TenantConversationStore,
)
from ticket_agent.api.ui_stream import ui_stream_response
from ticket_agent.auth import CallerTenant
from ticket_agent.constants.chat import EMPTY_MESSAGE_DETAIL, UNSUPPORTED_ROLE_DETAIL
from ticket_agent.constants.conversations import (
    AWAITING_TOOL_RESPONSE_DETAIL,
    CONVERSATION_ID_MAX_LENGTH,
    CONVERSATION_NOT_FOUND_DETAIL,
    CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE,
    INVALID_RESPONSE_OPTION_DETAIL,
    NO_SUCH_PENDING_CALL_DETAIL,
)
from ticket_agent.constants.ui_stream import UI_MESSAGE_ROLE_USER, UI_MESSAGE_TEXT_PART_TYPE
from ticket_agent.db.models import TenantConversation
from ticket_agent.db.session import DatabaseSession
from ticket_agent.llm.conversation import ToolCall, UserMessage
from ticket_agent.tools.registry import ToolRegistry

router = APIRouter()

# Path parameter shared by the routes that name a conversation; bounded like the column
# it is compared against.
ConversationIdPath = Annotated[str, Path(min_length=1, max_length=CONVERSATION_ID_MAX_LENGTH)]

# Path parameter naming a tool call; the adapter generates ids well under this bound.
ToolCallIdPath = Annotated[str, Path(min_length=1, max_length=128)]


class ConversationCreatedResponse(BaseModel):
    """What `POST /api/chat/new` returns: the id to use for the next calls."""

    id: str
    created_at: datetime


class ConversationMessageResponse(BaseModel):
    """One stored message: its role and the JSON content exactly as stored."""

    id: int
    role: str
    content: dict[str, Any]
    created_at: datetime


class PendingToolCallResponse(BaseModel):
    """The tool call a frozen conversation waits on, with the options the person has."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    options: list[str]


class ConversationResponse(BaseModel):
    """A conversation with its status, its messages oldest first, and any pending call."""

    id: str
    tenant_id: str
    status: str
    created_at: datetime
    pending_tool_call: PendingToolCallResponse | None
    messages: list[ConversationMessageResponse]


class UIMessagePart(BaseModel):
    """One part of an AI SDK UI message; only text parts are read, others are kept."""

    model_config = ConfigDict(extra="allow")

    type: str
    text: str | None = None


class UIMessage(BaseModel):
    """The AI SDK UI message shape the frontend sends: a role and a list of parts."""

    model_config = ConfigDict(extra="allow")

    role: str
    parts: list[UIMessagePart]


class PostMessageRequest(BaseModel):
    """Body of `POST /api/chat/{id}`: the one new message."""

    message: UIMessage


class ToolResponseRequest(BaseModel):
    """Body of the tool-call response route: which of the offered options was picked."""

    option: str


def conversation_response_from_model(
    conversation: TenantConversation, pending_call: ToolCall | None, registry: ToolRegistry
) -> ConversationResponse:
    """Copy a conversation row, its messages and its pending call into the response shape.

    Args:
        conversation: the ORM row, with its messages relationship.
        pending_call: the call the conversation waits on, or None when active.
        registry: the tools, for the options of the pending call.

    Returns:
        The response body for that conversation.
    """
    message_responses = []
    for row in conversation.messages:
        message_response = ConversationMessageResponse(
            id=row.id, role=row.role, content=row.content, created_at=row.created_at
        )
        message_responses.append(message_response)

    pending_response: PendingToolCallResponse | None = None
    is_frozen = pending_call is not None
    if is_frozen:
        tool = registry.get(pending_call.tool_name)
        pending_response = PendingToolCallResponse(
            call_id=pending_call.call_id,
            tool_name=pending_call.tool_name,
            arguments=dict(pending_call.arguments),
            options=list(tool.response_options),
        )

    conversation_response = ConversationResponse(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        status=conversation.status,
        created_at=conversation.created_at,
        pending_tool_call=pending_response,
        messages=message_responses,
    )

    return conversation_response


def text_of_user_message(message: UIMessage) -> str:
    """Join the text parts of a user message into the text sent to the model.

    Args:
        message: the message from the request body.

    Returns:
        The concatenated, stripped text.

    Raises:
        HTTPException: 400 when the role is not `user` or the text is empty.
    """
    is_user_message = message.role == UI_MESSAGE_ROLE_USER
    if not is_user_message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=UNSUPPORTED_ROLE_DETAIL)

    text_fragments = []
    for part in message.parts:
        is_text_part = part.type == UI_MESSAGE_TEXT_PART_TYPE and part.text is not None
        if is_text_part:
            text_fragments.append(part.text)

    joined_text = "".join(text_fragments)
    user_text = joined_text.strip()
    is_empty = user_text == ""
    if is_empty:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=EMPTY_MESSAGE_DETAIL)

    return user_text


def owned_conversation(
    store: TenantConversationStore, tenant_id: str, conversation_id: str
) -> TenantConversation:
    """Return the conversation if the caller's tenant owns it, else answer 404.

    Args:
        store: the store bound to the request's session.
        tenant_id: the caller's tenant.
        conversation_id: the id from the path.

    Returns:
        The conversation row.

    Raises:
        HTTPException: 404 for an id that does not exist or belongs to another tenant;
            one wording for both so the response does not confirm the id exists.
    """
    try:
        conversation = store.get(tenant_id, conversation_id)
    except ConversationNotFound as not_found:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=CONVERSATION_NOT_FOUND_DETAIL
        ) from not_found

    return conversation


def loop_dependencies_of(request: Request) -> LoopDependencies:
    """Collect what the loop needs from the application state.

    Args:
        request: the current request.

    Returns:
        Provider, registry, session factory and round bound as configured at startup.
    """
    application_state = request.app.state
    dependencies = LoopDependencies(
        provider=application_state.model_provider,
        registry=application_state.tool_registry,
        session_factory=application_state.session_factory,
        max_tool_rounds=application_state.settings.max_tool_rounds,
    )

    return dependencies


# Registered before the `{conversation_id}` routes so that the literal `new` is never
# read as an id.
@router.post("/api/chat/new", status_code=status.HTTP_201_CREATED)
def create_conversation(
    tenant: CallerTenant, session: DatabaseSession
) -> ConversationCreatedResponse:
    """Create an empty conversation owned by the calling tenant.

    Args:
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session.

    Returns:
        The new conversation's server-generated id and creation time.
    """
    store = TenantConversationStore(session)
    conversation = store.create(tenant.id)

    created_response = ConversationCreatedResponse(
        id=conversation.id, created_at=conversation.created_at
    )

    return created_response


@router.get("/api/chat/{conversation_id}")
def read_conversation(
    conversation_id: ConversationIdPath,
    tenant: CallerTenant,
    session: DatabaseSession,
    request: Request,
) -> ConversationResponse:
    """Return the conversation with its messages if the calling tenant owns it.

    Args:
        conversation_id: the id from the path.
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session.
        request: the current request, for the tool registry on the application state.

    Returns:
        The conversation, its messages oldest first, and the pending call if frozen.

    Raises:
        HTTPException: 404 when the id is unknown or belongs to another tenant.
    """
    store = TenantConversationStore(session)
    conversation = owned_conversation(store, tenant.id, conversation_id)
    pending_call = store.pending_tool_call(tenant.id, conversation_id)
    registry = request.app.state.tool_registry

    conversation_response = conversation_response_from_model(conversation, pending_call, registry)

    return conversation_response


@router.post("/api/chat/{conversation_id}")
def post_message(
    conversation_id: ConversationIdPath,
    post_request: PostMessageRequest,
    tenant: CallerTenant,
    session: DatabaseSession,
    request: Request,
) -> StreamingResponse:
    """Append the message to the caller's conversation and stream the agent's reply.

    Validation, the ownership check and the frozen check run before the stream opens,
    so a bad request, a foreign conversation or a conversation waiting on a tool call is
    answered with a real status code and nothing is stored.

    Args:
        conversation_id: the id from the path.
        post_request: the parsed body.
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session, used for the checks only.
        request: the current request, for the loop's dependencies on the app state.

    Returns:
        The AI SDK UI message stream of one assistant message.

    Raises:
        HTTPException: 400 for an unsupported role or empty text; 404 when the id is
            unknown or belongs to another tenant; 409 while the conversation waits for
            a tool response, naming the pending call id.
    """
    user_text = text_of_user_message(post_request.message)

    # Ownership is settled here, before anything is stored or streamed: a conversation
    # of another tenant is refused and nothing is written.
    store = TenantConversationStore(session)
    conversation = owned_conversation(store, tenant.id, conversation_id)

    # A frozen conversation takes no message: the pending call must be answered first,
    # and the answer goes through its own route, never through a chat message.
    is_frozen = conversation.status == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
    if is_frozen:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{AWAITING_TOOL_RESPONSE_DETAIL}: {conversation.pending_tool_call_id}",
        )

    dependencies = loop_dependencies_of(request)
    incoming_message = UserMessage(text=user_text)
    agent_events = run_turn(dependencies, tenant.id, conversation_id, incoming_message)
    response = ui_stream_response(agent_events)

    return response


@router.post("/api/chat/{conversation_id}/tool-calls/{tool_call_id}/response")
def respond_to_tool_call(
    conversation_id: ConversationIdPath,
    tool_call_id: ToolCallIdPath,
    tool_response: ToolResponseRequest,
    tenant: CallerTenant,
    session: DatabaseSession,
    request: Request,
) -> StreamingResponse:
    """Answer the tool call the conversation is frozen on and stream what follows.

    Only the option travels from the client; the call's arguments are the ones stored
    when the model made it. The checks run before the stream opens, so a wrong call
    id, a second answer to an already answered call, or an option the tool does not
    offer are refused with a status code and nothing runs.

    Args:
        conversation_id: the id from the path.
        tool_call_id: the call id from the path, compared with the stored pending id.
        tool_response: the parsed body with the chosen option.
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session, used for the checks only.
        request: the current request, for the loop's dependencies on the app state.

    Returns:
        The AI SDK UI message stream continuing the assistant's turn.

    Raises:
        HTTPException: 404 when the conversation is unknown or belongs to another
            tenant; 409 when no call with this id is awaiting a response; 400 when the
            option is not one the tool offers.
    """
    store = TenantConversationStore(session)
    owned_conversation(store, tenant.id, conversation_id)

    # The pending call is read from the conversation, never from the request: the id
    # in the path merely has to match it. Any mismatch, including a replay after the
    # call was answered, is the same refusal.
    pending_call = store.pending_tool_call(tenant.id, conversation_id)
    is_pending_match = pending_call is not None and pending_call.call_id == tool_call_id
    if not is_pending_match:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=NO_SUCH_PENDING_CALL_DETAIL)

    registry = request.app.state.tool_registry
    tool = registry.get(pending_call.tool_name)
    is_offered_option = tool_response.option in tool.response_options
    if not is_offered_option:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=INVALID_RESPONSE_OPTION_DETAIL)

    dependencies = loop_dependencies_of(request)
    agent_events = resume_turn(
        dependencies, tenant.id, conversation_id, pending_call, tool_response.option
    )
    response = ui_stream_response(agent_events)

    return response
