"""The chat endpoints: create a conversation, read it back, post a message to it.

Lifecycle: `POST /api/chat/new` creates a conversation for the calling tenant and
returns its id; `GET /api/chat/{id}` returns it with its messages; `POST /api/chat/{id}`
appends one user message and streams the agent's reply. The last two answer 404 for an
id that does not exist or belongs to another tenant, identically.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from ticket_agent.agent.loop import run_turn
from ticket_agent.agent.tenant_conversations import (
    ConversationNotFound,
    TenantConversationStore,
)
from ticket_agent.api.ui_stream import ui_stream_response
from ticket_agent.auth import CallerTenant
from ticket_agent.constants.chat import EMPTY_MESSAGE_DETAIL, UNSUPPORTED_ROLE_DETAIL
from ticket_agent.constants.conversations import (
    CONVERSATION_ID_MAX_LENGTH,
    CONVERSATION_NOT_FOUND_DETAIL,
)
from ticket_agent.constants.ui_stream import UI_MESSAGE_ROLE_USER, UI_MESSAGE_TEXT_PART_TYPE
from ticket_agent.db.models import TenantConversation
from ticket_agent.db.session import DatabaseSession
from ticket_agent.llm.conversation import UserMessage

router = APIRouter()

# Path parameter shared by the read and post routes; bounded like the column it is
# compared against.
ConversationIdPath = Annotated[str, Path(min_length=1, max_length=CONVERSATION_ID_MAX_LENGTH)]


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


class ConversationResponse(BaseModel):
    """A conversation with its messages, oldest first."""

    id: str
    tenant_id: str
    created_at: datetime
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


def conversation_response_from_model(conversation: TenantConversation) -> ConversationResponse:
    """Copy a conversation row and its messages into the response shape.

    Args:
        conversation: the ORM row, with its messages relationship.

    Returns:
        The response body for that conversation.
    """
    message_responses = []
    for row in conversation.messages:
        message_response = ConversationMessageResponse(
            id=row.id, role=row.role, content=row.content, created_at=row.created_at
        )
        message_responses.append(message_response)

    conversation_response = ConversationResponse(
        id=conversation.id,
        tenant_id=conversation.tenant_id,
        created_at=conversation.created_at,
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
    conversation_id: ConversationIdPath, tenant: CallerTenant, session: DatabaseSession
) -> ConversationResponse:
    """Return the conversation with its messages if the calling tenant owns it.

    Args:
        conversation_id: the id from the path.
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session.

    Returns:
        The conversation and its messages, oldest first.

    Raises:
        HTTPException: 404 when the id is unknown or belongs to another tenant.
    """
    store = TenantConversationStore(session)
    conversation = owned_conversation(store, tenant.id, conversation_id)
    conversation_response = conversation_response_from_model(conversation)

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

    Validation and the ownership check run before the stream opens, so a bad request
    or a foreign conversation id is answered with a real status code instead of an
    error inside the stream.

    Args:
        conversation_id: the id from the path.
        post_request: the parsed body.
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session, used for the ownership check only.
        request: the current request, for the provider and session factory on app state.

    Returns:
        The AI SDK UI message stream of one assistant message.

    Raises:
        HTTPException: 400 for an unsupported role or empty text; 404 when the id is
            unknown or belongs to another tenant.
    """
    user_text = text_of_user_message(post_request.message)

    # Ownership is settled here, before anything is stored or streamed: a conversation
    # of another tenant is refused and nothing is written.
    store = TenantConversationStore(session)
    owned_conversation(store, tenant.id, conversation_id)

    provider = request.app.state.model_provider
    session_factory = request.app.state.session_factory
    incoming_message = UserMessage(text=user_text)
    agent_events = run_turn(provider, session_factory, tenant.id, conversation_id, incoming_message)
    response = ui_stream_response(agent_events)

    return response
