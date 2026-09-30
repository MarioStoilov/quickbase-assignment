/**
 * The one module that speaks to the AI SDK's transport layer.
 *
 * A transport is what the AI SDK calls to send the conversation and receive the
 * stream. This one serves two backend routes. A new message from the person posts only
 * that message to `POST /api/chat/{id}`. The person's answer to a pending tool call
 * posts only the chosen option to `POST /api/chat/{id}/tool-calls/{call_id}/response`.
 * Both routes answer the same UI message stream, so the AI SDK parses both the same
 * way. The history is never sent: the backend holds it.
 */

import { DefaultChatTransport } from "ai";
import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";

import { conversationPath, tenantHeaders, toolResponsePath } from "../api/client";
import { REQUEST_BODY_TOOL_RESPONSE_KEY, START_PART_TYPE } from "../constants/stream";

/** The person's answer to the tool call the conversation is frozen on. */
export interface ToolResponse {
  toolCallId: string;
  option: string;
}

/** What the AI SDK hands to `sendMessages`. */
type SendMessagesOptions = Parameters<ChatTransport<UIMessage>["sendMessages"]>[0];

/** What `prepareSendMessagesRequest` receives; only the fields read here are named. */
interface OutgoingRequest {
  messages: UIMessage[];
  body: Record<string, unknown> | undefined;
}

/** What `prepareSendMessagesRequest` returns: the route and the body to post. */
interface PreparedRequest {
  api?: string;
  body: object;
}

// Thrown when the AI SDK asks to send while the newest message is not the person's;
// the transport has nothing to post in that case.
const NO_USER_MESSAGE_ERROR = "the newest message is not a user message";

/**
 * Build the request body that makes the transport answer a tool call.
 *
 * The AI SDK passes request bodies through to the transport untouched; the transport
 * recognises this key and switches routes.
 *
 * @param toolResponse - the call and the option the person picked.
 * @returns The body to pass as the request option.
 */
export function toolResponseBody(toolResponse: ToolResponse): Record<string, unknown> {
  const body = { [REQUEST_BODY_TOOL_RESPONSE_KEY]: toolResponse };

  return body;
}

/**
 * Check whether a value is a tool response.
 *
 * @param value - anything found under the tool response key.
 * @returns True when it names a call id and an option.
 */
function isToolResponse(value: unknown): value is ToolResponse {
  const isObject = typeof value === "object" && value !== null;
  if (!isObject) {
    return false;
  }

  const candidate: Partial<Record<keyof ToolResponse, unknown>> = value;
  const hasToolCallId = typeof candidate.toolCallId === "string";
  const hasOption = typeof candidate.option === "string";

  return hasToolCallId && hasOption;
}

/**
 * Read the tool response out of a request body, if the body carries one.
 *
 * @param body - the request options' body, or undefined.
 * @returns The tool response, or null for an ordinary message request.
 */
function toolResponseIn(body: object | undefined): ToolResponse | null {
  const hasBody = body !== undefined;
  if (!hasBody) {
    return null;
  }

  const bodyFields: Record<string, unknown> = { ...body };
  const candidate = bodyFields[REQUEST_BODY_TOOL_RESPONSE_KEY];
  const isResponse = isToolResponse(candidate);
  if (!isResponse) {
    return null;
  }

  return candidate;
}

/**
 * Decide the route and body of one request from what the AI SDK is sending.
 *
 * @param conversationId - the conversation the transport is bound to.
 * @param request - the messages and the body the AI SDK passes.
 * @returns The tool response route with the option, or the message route with the
 *   newest user message.
 * @throws Error when there is no tool response and the newest message is not a user
 *   message.
 */
function prepareRequest(conversationId: string, request: OutgoingRequest): PreparedRequest {
  const toolResponse = toolResponseIn(request.body);
  const isToolResponseRequest = toolResponse !== null;

  if (isToolResponseRequest) {
    const responsePath = toolResponsePath(conversationId, toolResponse.toolCallId);
    const responseRequest: PreparedRequest = {
      api: responsePath,
      body: { option: toolResponse.option },
    };

    return responseRequest;
  }

  const newestMessage = request.messages.at(-1);
  const isUserMessage = newestMessage?.role === "user";
  if (!isUserMessage) {
    throw new Error(NO_USER_MESSAGE_ERROR);
  }

  const messageRequest: PreparedRequest = { body: { message: newestMessage } };

  return messageRequest;
}

/**
 * Build a transform that removes the message id from the stream's `start` part.
 *
 * The AI SDK continues the newest assistant message, instead of appending a new one,
 * only while the incoming message keeps that message's id. The backend generates a
 * fresh id for every stream, so on the tool response route, whose stream continues
 * the turn that asked, the id is dropped.
 *
 * @returns A transform stream that passes every other part through unchanged.
 */
function withoutStartMessageId(): TransformStream<UIMessageChunk, UIMessageChunk> {
  const transform = new TransformStream<UIMessageChunk, UIMessageChunk>({
    transform(chunk, controller): void {
      const isStart = chunk.type === START_PART_TYPE;
      if (!isStart) {
        controller.enqueue(chunk);
        return;
      }

      const startWithoutId: UIMessageChunk = {
        type: chunk.type,
        messageMetadata: chunk.messageMetadata,
      };
      controller.enqueue(startWithoutId);
    },
  });

  return transform;
}

/** The transport of one conversation: routes each request and parses the stream. */
export class ConversationTransport extends DefaultChatTransport<UIMessage> {
  /**
   * Bind the transport to one tenant and one conversation.
   *
   * @param tenantId - sent as the tenant header with every request.
   * @param conversationId - the conversation every request addresses.
   */
  constructor(tenantId: string, conversationId: string) {
    super({
      api: conversationPath(conversationId),
      headers: tenantHeaders(tenantId),
      prepareSendMessagesRequest: (request): PreparedRequest =>
        prepareRequest(conversationId, request),
    });
  }

  /**
   * Send one request and return its parsed stream.
   *
   * A tool response continues the assistant message that asked, so its stream has the
   * server's message id removed; a new message starts a new assistant message.
   *
   * @param options - what the AI SDK passes: the messages, the request body, the abort signal.
   * @returns The stream of UI message parts.
   * @throws Error when the backend answers with an error status; the message carries
   *   the response body.
   */
  override async sendMessages(
    options: SendMessagesOptions,
  ): Promise<ReadableStream<UIMessageChunk>> {
    const toolResponse = toolResponseIn(options.body);
    const isContinuation = toolResponse !== null;

    const stream = await super.sendMessages(options);
    if (!isContinuation) {
      return stream;
    }

    const continuationStream = stream.pipeThrough(withoutStartMessageId());

    return continuationStream;
  }
}
