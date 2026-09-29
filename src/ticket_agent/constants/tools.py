"""What every tool shares: the error convention and the loop's messages to the model.

Constants that belong to one tool (its name, argument keys, response options) live in
that tool's sub-package under `tools/`, next to the code that uses them.
"""

# Key under which every tool result reports a failure to the model. Its presence is what
# marks a result as an error; a successful result never carries it.
RESULT_ERROR_KEY = "error"

# Result text when the model requests a tool the registry does not hold.
UNKNOWN_TOOL_ERROR = "no such tool"

# Result text when the loop reaches its round limit with tool calls still coming.
TOOL_ROUND_LIMIT_ERROR = "too many tool calls in one turn; the request was stopped"
