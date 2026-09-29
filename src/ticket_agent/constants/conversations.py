"""Storage vocabulary and limits of tenant conversations."""

# Value of a stored message's `role` column for text typed by the person in the chat.
MESSAGE_ROLE_USER = "user"

# Value of a stored message's `role` column for one model turn (its text and tool calls).
MESSAGE_ROLE_ASSISTANT = "assistant"

# Value of a stored message's `role` column for the outcome of one tool call.
MESSAGE_ROLE_TOOL = "tool"

# Longest conversation id, in characters, for the column and the path parameter. The
# server generates 32-character UUID hex ids; the margin leaves room for another scheme
# without an unbounded column.
CONVERSATION_ID_MAX_LENGTH = 64

# Error text answered for a conversation id that does not exist or belongs to another
# tenant, one wording for both so the response does not confirm the id exists.
CONVERSATION_NOT_FOUND_DETAIL = "conversation not found"
