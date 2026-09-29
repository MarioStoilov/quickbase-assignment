"""Tenant-scoped access to conversations and their message history.

Every public method takes the caller's `tenant_id` as a required argument and puts it in
the WHERE clause, the same rule as `TicketRepository`. A conversation id is supplied by
the client and bound to the tenant when first seen; from then on only that tenant can
read or extend it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticket_agent.agent.message_serialisation import (
    message_from_role_and_content,
    role_and_content_of,
)
from ticket_agent.db.models import ConversationMessage, TenantConversation
from ticket_agent.llm.conversation import Message


class ConversationNotFound(Exception):
    """The conversation id is not visible to the caller's tenant."""

    def __init__(self, conversation_id: str) -> None:
        """Record the id that was requested."""
        super().__init__(f"conversation {conversation_id} not found")
        self.conversation_id = conversation_id


class TenantConversationStore:
    """Tenant-scoped reads and appends over the conversation tables for one session.

    Write methods commit before returning.
    """

    def __init__(self, session: Session) -> None:
        """Bind the store to `session`; the caller owns the session's lifetime."""
        self._session = session

    def get_or_create(self, tenant_id: str, conversation_id: str) -> TenantConversation:
        """Return the conversation `conversation_id` of `tenant_id`, creating it if new.

        An id that already exists under another tenant is reported as not found rather
        than created, so the client-supplied id can never move a conversation between
        tenants. Unlike tickets, a missing id is not an error here: it is how a new
        chat starts.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            conversation_id: the id the client chose for this chat.

        Returns:
            The existing or newly created conversation row.

        Raises:
            ConversationNotFound: the id belongs to another tenant.
        """
        statement = select(TenantConversation).where(TenantConversation.id == conversation_id)
        conversation = self._session.scalars(statement).first()
        is_known = conversation is not None
        is_foreign = is_known and conversation.tenant_id != tenant_id

        # The foreign check precedes creation so that the id is never re-bound.
        if is_foreign:
            raise ConversationNotFound(conversation_id)

        if is_known:
            return conversation

        conversation = TenantConversation(id=conversation_id, tenant_id=tenant_id)
        self._session.add(conversation)
        self._session.commit()

        return conversation

    def history(self, tenant_id: str, conversation_id: str) -> list[Message]:
        """Return every message of the conversation, oldest first.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            conversation_id: the conversation to read.

        Returns:
            The rebuilt history messages; empty for a conversation with no messages.

        Raises:
            ConversationNotFound: the id does not exist or belongs to another tenant.
        """
        conversation = self._get(tenant_id, conversation_id)

        messages = []
        for row in conversation.messages:
            message = message_from_role_and_content(row.role, row.content)
            messages.append(message)

        return messages

    def append(self, tenant_id: str, conversation_id: str, message: Message) -> None:
        """Store `message` as the newest entry of the conversation and commit.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            conversation_id: the conversation to extend.
            message: the user, assistant or tool-result message to store.

        Raises:
            ConversationNotFound: the id does not exist or belongs to another tenant.
        """
        conversation = self._get(tenant_id, conversation_id)
        role, content = role_and_content_of(message)

        row = ConversationMessage(
            tenant_conversation_id=conversation.id, role=role, content=content
        )
        self._session.add(row)
        self._session.commit()

    def _get(self, tenant_id: str, conversation_id: str) -> TenantConversation:
        """Return the conversation if it belongs to `tenant_id`.

        Args:
            tenant_id: the caller's tenant.
            conversation_id: the id to look up.

        Returns:
            The conversation row.

        Raises:
            ConversationNotFound: the id does not exist or belongs to another tenant.
        """
        statement = (
            select(TenantConversation)
            .where(TenantConversation.tenant_id == tenant_id)
            .where(TenantConversation.id == conversation_id)
        )
        conversation = self._session.scalars(statement).first()
        is_visible_to_tenant = conversation is not None

        if not is_visible_to_tenant:
            raise ConversationNotFound(conversation_id)

        return conversation
