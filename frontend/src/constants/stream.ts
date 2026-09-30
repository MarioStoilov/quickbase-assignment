/**
 * Vocabulary of the AI SDK UI message stream and message parts the frontend reads.
 *
 * The standard part types and states are fixed by the protocol; the custom data part is
 * the backend's own and is spelled identically in its `constants/ui_stream.py`.
 */

// Type of the custom data part the backend emits when the stream stops on a tool call
// that needs the person's answer. Its payload names the call, the tool and the options.
export const TOOL_RESPONSE_REQUIRED_PART_TYPE = "data-tool-response-required";

// Type of the part that opens an assistant message in the stream.
export const START_PART_TYPE = "start";

// Prefix of the part type the AI SDK gives a tool call; the tool name follows it.
export const TOOL_PART_TYPE_PREFIX = "tool-";

// State of a tool part whose arguments are known and which has no result yet.
export const TOOL_PART_STATE_INPUT_AVAILABLE = "input-available";

// State of a tool part whose result has arrived.
export const TOOL_PART_STATE_OUTPUT_AVAILABLE = "output-available";

// Key under which every backend tool result reports a failure; its presence is what
// marks a result as an error (the backend's `RESULT_ERROR_KEY`).
export const TOOL_RESULT_ERROR_KEY = "error";

// Key in the request body under which the transport carries a tool response, so that
// one transport serves both the message route and the tool response route.
export const REQUEST_BODY_TOOL_RESPONSE_KEY = "toolResponse";
