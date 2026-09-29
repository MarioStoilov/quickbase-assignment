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
