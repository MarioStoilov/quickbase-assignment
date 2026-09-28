"""Model provider defaults and the provider-neutral vocabulary of a turn."""

# Gemini model used when TICKET_AGENT_GEMINI_MODEL_ID is not set. A pinned id rather
# than a "latest" alias so that behaviour does not change underneath a reviewer. Google's
# quickstart recommends gemini-3.8-flash, but during development that model answered
# "high demand" (503) on the free tier for minutes at a time while 3.6 answered at once.
DEFAULT_GEMINI_MODEL_ID = "gemini-3.6-flash"

# The model produced a complete answer and stopped on its own.
FINISH_REASON_STOP = "stop"

# The model requested one or more tool calls; the turn resumes once results are given.
FINISH_REASON_TOOL_CALLS = "tool_calls"

# The model hit its output token limit; the answer is cut off.
FINISH_REASON_LENGTH = "length"

# The provider refused to answer or cut the answer short (safety filter, blocked
# prompt, recitation); `TurnFinished.detail` carries the provider's own reason.
FINISH_REASON_BLOCKED = "blocked"

# Prefix of the ids the adapter generates when the provider sends a function call
# without an id, so that every tool call can be referred to unambiguously.
GENERATED_CALL_ID_PREFIX = "call_"

# Key in a `provider_state` mapping under which the Gemini adapter keeps the
# base64-encoded thought signature a part arrived with. Gemini 3 models refuse a history
# whose function-call parts lack the signature they were streamed with.
THOUGHT_SIGNATURE_KEY = "thought_signature"

# HTTP status codes the provider returns for transient conditions (quota window hit,
# model under high demand); a request failing with one of these is retried.
RETRYABLE_STATUS_CODES = frozenset({429, 503})

# How many times a turn is attempted in total before the transient error is raised.
MODEL_REQUEST_ATTEMPTS = 4

# Seconds waited before the second attempt; each further wait doubles.
MODEL_RETRY_INITIAL_DELAY_SECONDS = 2.0
