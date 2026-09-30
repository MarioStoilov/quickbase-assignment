"""`TenantConversationStore`: ownership on every access, the freeze, and the history."""

import pytest
from sqlalchemy.orm import Session

from ticket_agent.agent.tenant_conversations import (
    ConversationNotFound,
    TenantConversationStore,
)
from ticket_agent.constants.conversations import (
    CONVERSATION_STATUS_ACTIVE,
    CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE,
)
from ticket_agent.constants.seed import ACME_TENANT_ID, GLOBEX_TENANT_ID
from ticket_agent.llm.conversation import (
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)

# Length of the hex form of a UUID, which is what `create` generates.
UUID_HEX_LENGTH = 32


@pytest.fixture
def store(session: Session) -> TenantConversationStore:
    """A store over the seeded database."""
    conversation_store = TenantConversationStore(session)

    return conversation_store


def test_create_generates_a_uuid_id_bound_to_the_tenant(store: TenantConversationStore) -> None:
    """A new conversation has a server-made id, the tenant, and the active status."""
    conversation = store.create(ACME_TENANT_ID)

    assert len(conversation.id) == UUID_HEX_LENGTH
    assert conversation.tenant_id == ACME_TENANT_ID
    assert conversation.status == CONVERSATION_STATUS_ACTIVE
    assert conversation.pending_tool_call_id is None


def test_get_reports_a_foreign_conversation_like_a_missing_one(
    store: TenantConversationStore,
) -> None:
    """Globex's conversation and an unknown id raise the same error for Acme."""
    globex_conversation = store.create(GLOBEX_TENANT_ID)

    with pytest.raises(ConversationNotFound) as foreign_failure:
        store.get(ACME_TENANT_ID, globex_conversation.id)
    with pytest.raises(ConversationNotFound) as missing_failure:
        store.get(ACME_TENANT_ID, "no-such-id")

    foreign_text = str(foreign_failure.value).replace(globex_conversation.id, "ID")
    missing_text = str(missing_failure.value).replace("no-such-id", "ID")
    assert foreign_text == missing_text


def test_list_all_is_per_tenant_and_newest_first(store: TenantConversationStore) -> None:
    """Acme's list holds Acme's conversations, newest first, and none of Globex's."""
    first = store.create(ACME_TENANT_ID)
    second = store.create(ACME_TENANT_ID)
    store.create(GLOBEX_TENANT_ID)

    acme_conversations = store.list_all(ACME_TENANT_ID)
    listed_ids = [conversation.id for conversation in acme_conversations]

    assert set(listed_ids) == {first.id, second.id}
    assert (
        listed_ids[0] == second.id
        or acme_conversations[0].created_at >= acme_conversations[1].created_at
    )


def test_append_and_history_round_trip_every_message_kind(
    store: TenantConversationStore,
) -> None:
    """User, assistant (with calls and state) and tool-result messages come back equal."""
    conversation = store.create(ACME_TENANT_ID)
    call = ToolCall(
        call_id="call-1",
        tool_name="search_tickets",
        arguments={"query": "x"},
        provider_state={"thought_signature": "c2ln"},
    )
    messages = [
        UserMessage(text="hello"),
        AssistantMessage(text="", tool_calls=(call,), provider_state={"k": "v"}),
        ToolResultMessage(call_id="call-1", tool_name="search_tickets", result={"count": 0}),
        AssistantMessage(text="done"),
    ]

    for message in messages:
        store.append(ACME_TENANT_ID, conversation.id, message)

    assert store.history(ACME_TENANT_ID, conversation.id) == messages


def test_append_to_a_foreign_conversation_is_refused(store: TenantConversationStore) -> None:
    """Acme cannot write into Globex's conversation."""
    globex_conversation = store.create(GLOBEX_TENANT_ID)

    with pytest.raises(ConversationNotFound):
        store.append(ACME_TENANT_ID, globex_conversation.id, UserMessage(text="hi"))

    assert store.history(GLOBEX_TENANT_ID, globex_conversation.id) == []


def test_freeze_and_unfreeze_change_status_and_pending_call(
    store: TenantConversationStore,
) -> None:
    """Freezing records the call id and the waiting status; unfreezing clears both."""
    conversation = store.create(ACME_TENANT_ID)

    store.freeze_on_tool_call(ACME_TENANT_ID, conversation.id, "call-9")
    frozen = store.get(ACME_TENANT_ID, conversation.id)
    assert frozen.status == CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE
    assert frozen.pending_tool_call_id == "call-9"

    store.unfreeze(ACME_TENANT_ID, conversation.id)
    released = store.get(ACME_TENANT_ID, conversation.id)
    assert released.status == CONVERSATION_STATUS_ACTIVE
    assert released.pending_tool_call_id is None


def test_pending_tool_call_returns_the_stored_call_with_its_arguments(
    store: TenantConversationStore,
) -> None:
    """The pending call is read from the newest assistant message, arguments included."""
    conversation = store.create(ACME_TENANT_ID)
    call = ToolCall(
        call_id="call-2", tool_name="mutate_ticket", arguments={"ticket_id": 1, "action": "delete"}
    )
    store.append(ACME_TENANT_ID, conversation.id, AssistantMessage(tool_calls=(call,)))

    assert store.pending_tool_call(ACME_TENANT_ID, conversation.id) is None

    store.freeze_on_tool_call(ACME_TENANT_ID, conversation.id, "call-2")
    assert store.pending_tool_call(ACME_TENANT_ID, conversation.id) == call


def test_pending_tool_call_is_none_when_the_id_matches_no_stored_call(
    store: TenantConversationStore,
) -> None:
    """A frozen conversation whose call id is not in the history yields no call."""
    conversation = store.create(ACME_TENANT_ID)
    store.freeze_on_tool_call(ACME_TENANT_ID, conversation.id, "ghost-call")

    assert store.pending_tool_call(ACME_TENANT_ID, conversation.id) is None
