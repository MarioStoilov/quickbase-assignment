"""Stored rows and history messages convert back and forth without loss."""

import pytest

from ticket_agent.agent.message_serialisation import (
    message_from_role_and_content,
    role_and_content_of,
)
from ticket_agent.constants.conversations import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
)
from ticket_agent.llm.conversation import (
    AssistantMessage,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


@pytest.mark.parametrize(
    ("message", "expected_role"),
    [
        (UserMessage(text="hi"), MESSAGE_ROLE_USER),
        (
            AssistantMessage(
                text="calling",
                tool_calls=(
                    ToolCall(
                        call_id="c1",
                        tool_name="search_tickets",
                        arguments={"query": "q"},
                        provider_state={"thought_signature": "abc"},
                    ),
                ),
                provider_state={"thought_signature": "xyz"},
            ),
            MESSAGE_ROLE_ASSISTANT,
        ),
        (
            ToolResultMessage(call_id="c1", tool_name="search_tickets", result={"count": 1}),
            MESSAGE_ROLE_TOOL,
        ),
    ],
)
def test_round_trip_keeps_every_field(message: object, expected_role: str) -> None:
    """A message stored by role and content is rebuilt equal to the original."""
    role, content = role_and_content_of(message)
    rebuilt_message = message_from_role_and_content(role, content)

    assert role == expected_role
    assert rebuilt_message == message


def test_unknown_role_is_refused() -> None:
    """A row with a role the code does not know cannot be rebuilt silently."""
    with pytest.raises(ValueError, match="unknown stored message role"):
        message_from_role_and_content("system", {"text": "x"})
