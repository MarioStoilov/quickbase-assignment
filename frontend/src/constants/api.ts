/**
 * Paths, header names and storage keys of the backend API the frontend talks to.
 *
 * The paths mirror the routes in the backend's `api/` package; changing a route there
 * means changing it here.
 */

// Request header naming the tenant; the backend's only stand-in for authentication.
export const TENANT_HEADER_NAME = "X-Tenant-ID";

// Content type of every request body the frontend posts.
export const JSON_CONTENT_TYPE = "application/json";

// Public path listing the seeded tenants for the login screen; needs no tenant header.
export const TENANTS_PATH = "/api/tenants";

// Path listing the calling tenant's conversations, newest first.
export const CONVERSATIONS_PATH = "/api/chat";

// Path that creates a conversation for the calling tenant and returns its id.
export const NEW_CONVERSATION_PATH = "/api/chat/new";

// Prefix of every path that names a conversation; the id follows it.
export const CONVERSATION_PATH_PREFIX = "/api/chat";

// Path segment, after the conversation id, under which tool calls are addressed.
export const TOOL_CALLS_PATH_SEGMENT = "tool-calls";

// Path segment, after the tool call id, that answers the pending call.
export const TOOL_RESPONSE_PATH_SEGMENT = "response";

// Status value the backend gives a conversation frozen on a tool call; the same
// spelling as its `CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE`.
export const CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE = "awaiting_tool_response";

// Status code the backend answers for a conversation that is unknown or foreign.
export const NOT_FOUND_STATUS = 404;

// Key under which the chosen tenant id is kept for the browser session.
export const SESSION_STORAGE_TENANT_KEY = "ticket-agent.tenant-id";

// Key under which the open conversation id is kept for the browser session.
export const SESSION_STORAGE_CONVERSATION_KEY = "ticket-agent.conversation-id";
