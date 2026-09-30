/**
 * Every text the person sees that is not produced by the model or the backend.
 */

// Title shown above the chat and on the login screen.
export const APPLICATION_TITLE = "Ticket Agent";

// Login screen heading, above the tenant buttons.
export const LOGIN_PROMPT = "Choose the tenant to act as";

// Shown while the tenant list is being fetched.
export const LOADING_TENANTS_TEXT = "Loading tenants…";

// Shown while a conversation is being created or read back after a reload.
export const LOADING_CONVERSATION_TEXT = "Opening the conversation…";

// Shown in the chat area before the first message.
export const EMPTY_CONVERSATION_TEXT =
  "Ask about your tickets. Changes are only applied after you approve them here.";

// Placeholder of the message input.
export const COMPOSER_PLACEHOLDER = "Type a message";

// Placeholder of the message input while a tool call waits for the person's answer.
export const COMPOSER_BLOCKED_PLACEHOLDER = "Answer the pending tool call first";

// Label of the send button.
export const SEND_BUTTON_LABEL = "Send";

// Label of the button that starts a fresh conversation for the same tenant.
export const NEW_CONVERSATION_BUTTON_LABEL = "New conversation";

// Label of the button in the chat header that returns to the list of conversations.
export const CONVERSATIONS_BUTTON_LABEL = "Conversations";

// Heading of the list of the tenant's conversations.
export const CONVERSATIONS_HEADING = "Your conversations";

// Shown while the list of conversations is being fetched.
export const LOADING_CONVERSATIONS_TEXT = "Loading conversations…";

// Shown in place of the list when the tenant has no conversation yet.
export const NO_CONVERSATIONS_TEXT = "No conversations yet.";

// Shown as the preview of a conversation nobody has written to.
export const EMPTY_CONVERSATION_PREVIEW = "Empty conversation";

// Mark on a listed conversation that is frozen on a tool call.
export const CONVERSATION_WAITING_MARK = "Waiting for your answer";

// Label of the button that forgets the tenant and returns to the login screen.
export const LOGOUT_BUTTON_LABEL = "Log out";

// Prefix of the header line naming the tenant the chat acts as.
export const ACTING_AS_PREFIX = "Acting as";

// Heading of the trace box for one tool call; the tool name follows it.
export const TOOL_TRACE_HEADING = "Tool call";

// Label above the arguments in the trace box.
export const TOOL_TRACE_ARGUMENTS_LABEL = "Arguments";

// Label above the result in the trace box.
export const TOOL_TRACE_RESULT_LABEL = "Result";

// State word in the trace summary, and in place of the result, while the tool waits
// for the person's answer.
export const TOOL_TRACE_WAITING_TEXT = "Waiting for your answer";

// State word in the trace summary, and in place of the result, while the tool runs or
// its result is still in flight.
export const TOOL_TRACE_RUNNING_TEXT = "Running…";

// State word in the trace summary once the tool has a result that is not an error.
export const TOOL_TRACE_DONE_TEXT = "Done";

// State word in the trace summary once the tool has a result carrying the error key.
export const TOOL_TRACE_FAILED_TEXT = "Failed";

// Heading of the modal that asks the person to answer a tool call.
export const TOOL_RESPONSE_MODAL_HEADING = "The agent wants to run a tool";

// Sentence in the modal, before the tool name and its arguments.
export const TOOL_RESPONSE_MODAL_EXPLANATION =
  "Nothing runs until you pick an option. The arguments below are the ones that will be used.";

// Prefix of the error line shown under a message that ended in an error.
export const MESSAGE_ERROR_PREFIX = "The turn ended with an error";
