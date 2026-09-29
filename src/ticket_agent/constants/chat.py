"""Messages the chat endpoint and the agent loop answer when a turn cannot run normally."""

# Error text for a request whose message carries a role the endpoint does not accept.
UNSUPPORTED_ROLE_DETAIL = "only user messages are accepted"

# Error text for a request whose message has no text part or only blank text.
EMPTY_MESSAGE_DETAIL = "message contains no text"

# Shown in the chat when the provider refused or cut short an answer (safety filter,
# blocked prompt); the provider's own reason is appended after a colon.
BLOCKED_TURN_ERROR_TEXT = "the model declined to answer"

# Model calls one request may make before the loop stops with a tool error, counting the
# first call. Bounds a model that keeps requesting tools. Default of the setting
# TICKET_AGENT_MAX_TOOL_ROUNDS.
DEFAULT_MAX_TOOL_ROUNDS = 8
