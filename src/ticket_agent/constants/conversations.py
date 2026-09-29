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

# Status of a conversation that accepts new messages from the person.
CONVERSATION_STATUS_ACTIVE = "active"

# Status of a conversation halted on a tool call that needs the person's answer. No
# message is accepted until the call is resolved; see `agent.tool_responses`.
CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE = "awaiting_tool_response"

# Error text answered when a message arrives while the conversation waits for a tool
# response. The pending call id is appended so a client can show the prompt again.
AWAITING_TOOL_RESPONSE_DETAIL = "the conversation is waiting for a response to a tool call"

# Error text answered when a tool response arrives for a call that is not the one being
# waited on: the conversation is active, the id is stale, or it was answered already.
NO_SUCH_PENDING_CALL_DETAIL = "no tool call is awaiting a response under that id"

# Error text answered when the chosen option is not one the pending tool offers.
INVALID_RESPONSE_OPTION_DETAIL = "the chosen option is not offered by this tool call"
