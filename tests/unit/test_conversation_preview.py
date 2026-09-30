"""The preview a listed conversation carries: the first user message, bounded."""

from sqlalchemy.orm import Session

from ticket_agent.agent.tenant_conversations import TenantConversationStore
from ticket_agent.api.chat import preview_of
from ticket_agent.constants.conversations import (
    CONVERSATION_PREVIEW_ELLIPSIS,
    CONVERSATION_PREVIEW_MAX_LENGTH,
)
from ticket_agent.constants.seed import ACME_TENANT_ID
from ticket_agent.llm.conversation import AssistantMessage, UserMessage


def test_preview_is_empty_for_an_untouched_conversation(session: Session) -> None:
    """No user message yet means an empty preview."""
    store = TenantConversationStore(session)
    conversation = store.create(ACME_TENANT_ID)

    assert preview_of(conversation) == ""


def test_preview_is_the_first_user_message_not_a_later_one(session: Session) -> None:
    """The first user text is the preview, even after an assistant reply and a second text."""
    store = TenantConversationStore(session)
    conversation = store.create(ACME_TENANT_ID)
    store.append(ACME_TENANT_ID, conversation.id, UserMessage(text="first question"))
    store.append(ACME_TENANT_ID, conversation.id, AssistantMessage(text="answer"))
    store.append(ACME_TENANT_ID, conversation.id, UserMessage(text="second question"))

    session.expire_all()
    assert preview_of(store.get(ACME_TENANT_ID, conversation.id)) == "first question"


def test_preview_is_cut_and_marked_when_too_long(session: Session) -> None:
    """Text over the bound is cut at the bound, trailing space removed, and marked."""
    store = TenantConversationStore(session)
    conversation = store.create(ACME_TENANT_ID)
    long_text = "word " * CONVERSATION_PREVIEW_MAX_LENGTH
    store.append(ACME_TENANT_ID, conversation.id, UserMessage(text=long_text))

    session.expire_all()
    preview = preview_of(store.get(ACME_TENANT_ID, conversation.id))

    assert preview.endswith(CONVERSATION_PREVIEW_ELLIPSIS)
    assert len(preview) <= CONVERSATION_PREVIEW_MAX_LENGTH + len(CONVERSATION_PREVIEW_ELLIPSIS)
    assert not preview[:-1].endswith(" ")
