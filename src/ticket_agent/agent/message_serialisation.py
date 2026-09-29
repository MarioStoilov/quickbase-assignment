"""Convert provider-neutral history messages to stored rows and back.

The stored content is the message's fields as a JSON object, so a row can be rebuilt
into the same dataclass without a second schema. Which dataclass a row becomes is
decided by its `role` column.
"""

from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from ticket_agent.constants.conversations import (
    MESSAGE_ROLE_ASSISTANT,
    MESSAGE_ROLE_TOOL,
    MESSAGE_ROLE_USER,
)
from ticket_agent.llm.conversation import (
    AssistantMessage,
    Message,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


def role_and_content_of(message: Message) -> tuple[str, dict[str, Any]]:
    """Split a history message into the role and JSON content a row stores.

    Args:
        message: a user, assistant or tool-result message.

    Returns:
        The role value and a JSON-compatible dict of the message's fields.
    """
    content = asdict(message)

    if isinstance(message, UserMessage):
        role = MESSAGE_ROLE_USER
    elif isinstance(message, AssistantMessage):
        role = MESSAGE_ROLE_ASSISTANT
    else:
        role = MESSAGE_ROLE_TOOL

    return role, content


def message_from_role_and_content(role: str, content: Mapping[str, Any]) -> Message:
    """Rebuild the history message a row was made from.

    Args:
        role: the row's role value.
        content: the row's JSON content, as written by `role_and_content_of`.

    Returns:
        The message dataclass for that role.

    Raises:
        ValueError: `role` is not one of the stored role values.
    """
    if role == MESSAGE_ROLE_USER:
        user_message = UserMessage(text=content["text"])
        return user_message

    if role == MESSAGE_ROLE_ASSISTANT:
        tool_calls = []
        for stored_call in content["tool_calls"]:
            tool_call = ToolCall(
                call_id=stored_call["call_id"],
                tool_name=stored_call["tool_name"],
                arguments=stored_call["arguments"],
                provider_state=stored_call["provider_state"],
            )
            tool_calls.append(tool_call)

        assistant_message = AssistantMessage(
            text=content["text"],
            tool_calls=tuple(tool_calls),
            provider_state=content["provider_state"],
        )
        return assistant_message

    if role == MESSAGE_ROLE_TOOL:
        tool_result_message = ToolResultMessage(
            call_id=content["call_id"],
            tool_name=content["tool_name"],
            result=content["result"],
        )
        return tool_result_message

    raise ValueError(f"unknown stored message role '{role}'")
