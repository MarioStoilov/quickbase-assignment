/**
 * Rebuild AI SDK UI messages from a conversation as the backend stores it.
 *
 * Used after a reload: the stored rows become the messages the chat starts with, in
 * the same shape the stream would have produced, so the trace and the modal render
 * identically for a live turn and for a reloaded one.
 */

import type { UIMessage, UIMessagePart, UIDataTypes, UITools } from "ai";

import type { ConversationResponse, StoredMessage, StoredToolCall } from "../api/types";
import {
  TOOL_PART_STATE_INPUT_AVAILABLE,
  TOOL_PART_STATE_OUTPUT_AVAILABLE,
  TOOL_PART_TYPE_PREFIX,
  TOOL_RESPONSE_REQUIRED_PART_TYPE,
} from "../constants/stream";

/** A part of a UI message, with the default data and tool typing. */
type MessagePart = UIMessagePart<UIDataTypes, UITools>;

/**
 * Collect the stored tool results by the id of the call they answer.
 *
 * @param storedMessages - every stored message of the conversation.
 * @returns The result of each answered call.
 */
function toolResultsByCallId(
  storedMessages: StoredMessage[],
): Map<string, Record<string, unknown>> {
  const resultsByCallId = new Map<string, Record<string, unknown>>();

  for (const storedMessage of storedMessages) {
    const isToolResult = storedMessage.role === "tool";
    if (isToolResult) {
      resultsByCallId.set(storedMessage.content.call_id, storedMessage.content.result);
    }
  }

  return resultsByCallId;
}

/**
 * Build the tool part of one stored call, with its result when one is stored.
 *
 * @param storedCall - the call as the model made it.
 * @param result - the stored result, or undefined when the call is unanswered.
 * @returns A tool part in the state the stream would have left it in.
 */
function toolPartFrom(
  storedCall: StoredToolCall,
  result: Record<string, unknown> | undefined,
): MessagePart {
  const partType = `${TOOL_PART_TYPE_PREFIX}${storedCall.tool_name}` as const;
  const hasResult = result !== undefined;

  if (hasResult) {
    const answeredPart: MessagePart = {
      type: partType,
      toolCallId: storedCall.call_id,
      state: TOOL_PART_STATE_OUTPUT_AVAILABLE,
      input: storedCall.arguments,
      output: result,
    };

    return answeredPart;
  }

  const unansweredPart: MessagePart = {
    type: partType,
    toolCallId: storedCall.call_id,
    state: TOOL_PART_STATE_INPUT_AVAILABLE,
    input: storedCall.arguments,
  };

  return unansweredPart;
}

/**
 * Build the UI messages of a conversation from its stored rows.
 *
 * A user row becomes a user message. An assistant row becomes an assistant message
 * with its text and one tool part per call; tool rows are folded into those parts as
 * results and produce no message of their own. When the conversation is frozen, the
 * message holding the pending call also gets the same response-required data part
 * the stream emits, so the modal opens on reload.
 *
 * @param conversation - the conversation as returned by `GET /api/chat/{id}`.
 * @returns The messages, oldest first.
 */
export function uiMessagesFromConversation(conversation: ConversationResponse): UIMessage[] {
  const resultsByCallId = toolResultsByCallId(conversation.messages);
  const pendingCall = conversation.pending_tool_call;
  const messages: UIMessage[] = [];

  for (const storedMessage of conversation.messages) {
    const messageId = String(storedMessage.id);

    if (storedMessage.role === "user") {
      const userMessage: UIMessage = {
        id: messageId,
        role: "user",
        parts: [{ type: "text", text: storedMessage.content.text }],
      };
      messages.push(userMessage);
      continue;
    }

    if (storedMessage.role === "tool") {
      continue;
    }

    const parts: MessagePart[] = [];
    const hasText = storedMessage.content.text !== "";
    if (hasText) {
      parts.push({ type: "text", text: storedMessage.content.text, state: "done" });
    }

    for (const storedCall of storedMessage.content.tool_calls) {
      const result = resultsByCallId.get(storedCall.call_id);
      const toolPart = toolPartFrom(storedCall, result);
      parts.push(toolPart);

      // The frozen call carries the same data part the stream ends on, so the modal
      // derives its state from the messages alone, live or reloaded.
      const isPendingCall = pendingCall !== null && pendingCall.call_id === storedCall.call_id;
      if (isPendingCall) {
        parts.push({
          type: TOOL_RESPONSE_REQUIRED_PART_TYPE,
          data: {
            toolCallId: pendingCall.call_id,
            toolName: pendingCall.tool_name,
            options: pendingCall.options,
          },
        });
      }
    }

    const assistantMessage: UIMessage = { id: messageId, role: "assistant", parts };
    messages.push(assistantMessage);
  }

  return messages;
}
