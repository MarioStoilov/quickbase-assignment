"""Vocabulary of the AI SDK UI message stream and UI message shapes the chat speaks.

Part types and field names are fixed by the protocol
(https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol); they are constants so the encoder
and the request parsing use one spelling.
"""

# Response header that tells the AI SDK client which stream protocol follows.
UI_STREAM_HEADER_NAME = "x-vercel-ai-ui-message-stream"

# The protocol version this encoder produces.
UI_STREAM_HEADER_VALUE = "v1"

# Media type of the response body; the parts are sent as server-sent events.
UI_STREAM_MEDIA_TYPE = "text/event-stream"

# Prefix of every server-sent event line carrying a part.
SSE_DATA_PREFIX = "data: "

# What ends one server-sent event.
SSE_EVENT_TERMINATOR = "\n\n"

# Payload of the last event; the client closes the stream when it sees it.
STREAM_TERMINATOR = "[DONE]"

# Part type opening one assistant message; carries the message id.
PART_TYPE_START = "start"

# Part type opening one text block of the message; carries the block id.
PART_TYPE_TEXT_START = "text-start"

# Part type carrying one fragment of a text block.
PART_TYPE_TEXT_DELTA = "text-delta"

# Part type closing a text block.
PART_TYPE_TEXT_END = "text-end"

# Part type reporting a failure; the client shows the text and marks the message.
PART_TYPE_ERROR = "error"

# Part type closing the assistant message.
PART_TYPE_FINISH = "finish"

# Field naming the part's type, present on every part.
FIELD_TYPE = "type"

# Field carrying the assistant message id on the start part.
FIELD_MESSAGE_ID = "messageId"

# Field carrying the text block id on text parts.
FIELD_ID = "id"

# Field carrying the fragment on a text-delta part.
FIELD_DELTA = "delta"

# Field carrying the message on an error part.
FIELD_ERROR_TEXT = "errorText"

# Type of a UI message part that holds typed text, in the request body.
UI_MESSAGE_TEXT_PART_TYPE = "text"

# Role of a UI message written by the person in the chat, in the request body.
UI_MESSAGE_ROLE_USER = "user"

# Part type announcing a tool call with its complete arguments; the trace shows it.
PART_TYPE_TOOL_INPUT_AVAILABLE = "tool-input-available"

# Part type carrying the result of a tool call that has run.
PART_TYPE_TOOL_OUTPUT_AVAILABLE = "tool-output-available"

# Custom data part (the protocol reserves the `data-` prefix for application parts)
# telling the client that the stream stopped on a tool call awaiting the person's
# answer, and which options the tool offers.
PART_TYPE_TOOL_RESPONSE_REQUIRED = "data-tool-response-required"

# Field carrying the tool call id on tool parts and on the response-required part.
FIELD_TOOL_CALL_ID = "toolCallId"

# Field carrying the tool name on a tool-input-available part.
FIELD_TOOL_NAME = "toolName"

# Field carrying the model's arguments on a tool-input-available part.
FIELD_INPUT = "input"

# Field carrying the result on a tool-output-available part.
FIELD_OUTPUT = "output"

# Field carrying the payload of a custom data part.
FIELD_DATA = "data"

# Key inside the response-required payload listing the options the person may pick.
DATA_KEY_OPTIONS = "options"

# Key inside the response-required payload naming the tool, for the client's prompt.
DATA_KEY_TOOL_NAME = "toolName"
