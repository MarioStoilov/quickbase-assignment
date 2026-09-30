/**
 * Shapes of the backend's JSON responses, mirroring its pydantic response models.
 */

/** One tenant as listed by `GET /api/tenants`. */
export interface TenantSummary {
  id: string;
  display_name: string;
}

/** What `POST /api/chat/new` returns. */
export interface ConversationCreated {
  id: string;
  created_at: string;
}

/** One tool call inside a stored assistant message. */
export interface StoredToolCall {
  call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  provider_state: Record<string, unknown>;
}

/** Stored content of a message the person typed. */
export interface StoredUserContent {
  text: string;
}

/** Stored content of one model turn: its text and the tool calls it made. */
export interface StoredAssistantContent {
  text: string;
  tool_calls: StoredToolCall[];
  provider_state: Record<string, unknown>;
}

/** Stored content of one tool result. */
export interface StoredToolResultContent {
  call_id: string;
  tool_name: string;
  result: Record<string, unknown>;
}

/** Fields every stored message row carries besides its role and content. */
interface StoredMessageBase {
  id: number;
  created_at: string;
}

/** One stored message as returned inside `GET /api/chat/{id}`; the role picks the content. */
export type StoredMessage =
  | (StoredMessageBase & { role: "user"; content: StoredUserContent })
  | (StoredMessageBase & { role: "assistant"; content: StoredAssistantContent })
  | (StoredMessageBase & { role: "tool"; content: StoredToolResultContent });

/** The tool call a frozen conversation waits on, with the options the person has. */
export interface PendingToolCall {
  call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  options: string[];
}

/** What `GET /api/chat/{id}` returns. */
export interface ConversationResponse {
  id: string;
  tenant_id: string;
  status: string;
  created_at: string;
  pending_tool_call: PendingToolCall | null;
  messages: StoredMessage[];
}
