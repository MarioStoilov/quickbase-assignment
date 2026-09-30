/**
 * The plain JSON calls to the backend: tenant list, conversation create and read.
 *
 * Streaming requests go through the conversation transport instead; this module covers
 * everything that answers with one JSON body.
 */

import {
  CONVERSATION_PATH_PREFIX,
  CONVERSATIONS_PATH,
  JSON_CONTENT_TYPE,
  NEW_CONVERSATION_PATH,
  TENANT_HEADER_NAME,
  TENANTS_PATH,
  TOOL_CALLS_PATH_SEGMENT,
  TOOL_RESPONSE_PATH_SEGMENT,
} from "../constants/api";
import type {
  ConversationCreated,
  ConversationResponse,
  ConversationSummary,
  TenantSummary,
} from "./types";

/** A response the backend answered with an error status. */
export class ApiError extends Error {
  readonly status: number;

  /**
   * Build the error from the status and the body's `detail`, or the status text.
   *
   * @param status - the HTTP status code.
   * @param detail - the backend's explanation, when the body carried one.
   */
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Shape of the body FastAPI sends with an error status. */
interface ErrorBody {
  detail?: unknown;
}

/**
 * Parse a response body as the type the backend's response model promises.
 *
 * The backend's pydantic models are the contract; the shape is not validated again
 * here, so a backend change that alters a response model must be mirrored in `types.ts`.
 *
 * @param response - a response whose `ok` is true.
 * @returns The parsed body.
 */
async function jsonBodyOf<Body>(response: Response): Promise<Body> {
  const parsedBody: unknown = await response.json();
  const body = parsedBody as Body;

  return body;
}

/**
 * Turn an error response into an `ApiError` carrying the backend's explanation.
 *
 * @param response - a response whose `ok` is false.
 * @returns The error to throw.
 */
async function apiErrorFrom(response: Response): Promise<ApiError> {
  let detail = response.statusText;

  try {
    const body = await jsonBodyOf<ErrorBody>(response);
    const bodyDetail = body.detail;
    const hasDetail = typeof bodyDetail === "string";
    if (hasDetail) {
      detail = bodyDetail;
    }
  } catch {
    // A body that is not JSON keeps the status text as the explanation.
  }

  const apiError = new ApiError(response.status, detail);

  return apiError;
}

/**
 * Build the headers every tenant-scoped request carries.
 *
 * @param tenantId - the tenant the person acts as.
 * @returns The tenant header and the JSON content type.
 */
export function tenantHeaders(tenantId: string): Record<string, string> {
  const headers = {
    [TENANT_HEADER_NAME]: tenantId,
    "Content-Type": JSON_CONTENT_TYPE,
  };

  return headers;
}

/**
 * Build the path of one conversation.
 *
 * @param conversationId - the server-generated conversation id.
 * @returns The path used to read the conversation and to post messages to it.
 */
export function conversationPath(conversationId: string): string {
  const path = `${CONVERSATION_PATH_PREFIX}/${conversationId}`;

  return path;
}

/**
 * Build the path that answers a pending tool call of one conversation.
 *
 * @param conversationId - the conversation frozen on the call.
 * @param toolCallId - the id of the pending call.
 * @returns The path the chosen option is posted to.
 */
export function toolResponsePath(conversationId: string, toolCallId: string): string {
  const basePath = conversationPath(conversationId);
  const path = `${basePath}/${TOOL_CALLS_PATH_SEGMENT}/${toolCallId}/${TOOL_RESPONSE_PATH_SEGMENT}`;

  return path;
}

/**
 * Fetch the tenants the login screen offers.
 *
 * @returns The seeded tenants, in the backend's order.
 * @throws ApiError when the backend answers with an error status.
 */
export async function listTenants(): Promise<TenantSummary[]> {
  const response = await fetch(TENANTS_PATH);
  const isOk = response.ok;
  if (!isOk) {
    throw await apiErrorFrom(response);
  }

  const tenants = await jsonBodyOf<TenantSummary[]>(response);

  return tenants;
}

/**
 * List the tenant's conversations, newest first.
 *
 * @param tenantId - the tenant the person acts as.
 * @returns One summary per conversation; empty when there are none.
 * @throws ApiError when the backend answers with an error status.
 */
export async function listConversations(tenantId: string): Promise<ConversationSummary[]> {
  const headers = tenantHeaders(tenantId);
  const response = await fetch(CONVERSATIONS_PATH, { headers });
  const isOk = response.ok;
  if (!isOk) {
    throw await apiErrorFrom(response);
  }

  const conversations = await jsonBodyOf<ConversationSummary[]>(response);

  return conversations;
}

/**
 * Create an empty conversation for the tenant.
 *
 * @param tenantId - the tenant the person acts as.
 * @returns The new conversation's id and creation time.
 * @throws ApiError when the backend answers with an error status.
 */
export async function createConversation(tenantId: string): Promise<ConversationCreated> {
  const headers = tenantHeaders(tenantId);
  const response = await fetch(NEW_CONVERSATION_PATH, { method: "POST", headers });
  const isOk = response.ok;
  if (!isOk) {
    throw await apiErrorFrom(response);
  }

  const created = await jsonBodyOf<ConversationCreated>(response);

  return created;
}

/**
 * Read a conversation with its stored messages and pending tool call, if any.
 *
 * @param tenantId - the tenant the person acts as.
 * @param conversationId - the conversation to read.
 * @returns The conversation as the backend stores it.
 * @throws ApiError with status 404 when the id is unknown or belongs to another tenant.
 */
export async function readConversation(
  tenantId: string,
  conversationId: string,
): Promise<ConversationResponse> {
  const headers = tenantHeaders(tenantId);
  const path = conversationPath(conversationId);
  const response = await fetch(path, { headers });
  const isOk = response.ok;
  if (!isOk) {
    throw await apiErrorFrom(response);
  }

  const conversation = await jsonBodyOf<ConversationResponse>(response);

  return conversation;
}
