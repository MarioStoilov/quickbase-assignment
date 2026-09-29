"""The streaming chat endpoint: one request per user message, one streamed reply."""

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

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
from ticket_agent.db.session import DatabaseSession
from ticket_agent.llm.conversation import UserMessage

router = APIRouter()


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


class ChatRequest(BaseModel):
    """Body of `POST /api/chat`: which conversation, and the one new message."""

    model_config = ConfigDict(populate_by_name=True)

    tenant_conversation_id: str = Field(
        alias="tenantConversationId", min_length=1, max_length=CONVERSATION_ID_MAX_LENGTH
    )
    message: UIMessage


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


@router.post("/api/chat")
def chat(
    chat_request: ChatRequest, tenant: CallerTenant, session: DatabaseSession, request: Request
) -> StreamingResponse:
    """Append the message to the caller's conversation and stream the agent's reply.

    Validation and the conversation ownership check run before the stream opens, so a
    bad request or a foreign conversation id is answered with a real status code
    instead of an error inside the stream.

    Args:
        chat_request: the parsed body.
        tenant: the tenant resolved from the `X-Tenant-ID` header.
        session: per-request database session, used for the ownership check only.
        request: the current request, for the provider and session factory on app state.

    Returns:
        The AI SDK UI message stream of one assistant message.

    Raises:
        HTTPException: 400 for an unsupported role or empty text; 404 when the
            conversation id belongs to another tenant.
    """
    user_text = text_of_user_message(chat_request.message)
    conversation_id = chat_request.tenant_conversation_id

    # Ownership is settled here, before anything is stored or streamed: a conversation
    # id that exists under another tenant is refused and nothing is written.
    store = TenantConversationStore(session)
    try:
        store.get_or_create(tenant.id, conversation_id)
    except ConversationNotFound as not_found:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=CONVERSATION_NOT_FOUND_DETAIL
        ) from not_found

    provider = request.app.state.model_provider
    session_factory = request.app.state.session_factory
    incoming_message = UserMessage(text=user_text)
    agent_events = run_turn(provider, session_factory, tenant.id, conversation_id, incoming_message)
    response = ui_stream_response(agent_events)

    return response
