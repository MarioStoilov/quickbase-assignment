"""Storage vocabulary and limits of tenant conversations."""

# Value of a stored message's `role` column for text typed by the person in the chat.
MESSAGE_ROLE_USER = "user"

# Value of a stored message's `role` column for one model turn (its text and tool calls).
MESSAGE_ROLE_ASSISTANT = "assistant"

# Value of a stored message's `role` column for the outcome of one tool call.
MESSAGE_ROLE_TOOL = "tool"

# Longest conversation id accepted from the client, in characters. The frontend sends a
# UUID (36 characters) per chat; the margin admits other id schemes without leaving the
# column unbounded.
CONVERSATION_ID_MAX_LENGTH = 64

# Error text answered when the conversation id names a conversation of another tenant.
CONVERSATION_NOT_FOUND_DETAIL = "conversation not found"
