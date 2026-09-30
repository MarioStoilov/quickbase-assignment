/**
 * Find the tool call, if any, that the conversation is waiting on the person for.
 *
 * The answer is derived from the messages alone: the newest assistant message holds a
 * response-required data part naming a call, and that call's tool part has no result
 * yet. Once the backend streams the result, the tool part gains an output and the
 * pending state disappears without any further bookkeeping.
 */

import { isToolUIPart } from "ai";
import type { UIMessage } from "ai";

import {
  TOOL_PART_STATE_INPUT_AVAILABLE,
  TOOL_RESPONSE_REQUIRED_PART_TYPE,
} from "../constants/stream";

/** The call the person must answer, with what the modal shows and offers. */
export interface PendingToolResponse {
  toolCallId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  options: string[];
}

/** Payload of the response-required data part as the backend emits it. */
interface ToolResponseRequiredPayload {
  toolCallId: string;
  toolName: string;
  options: string[];
}

/**
 * Check whether a value is the payload of a response-required part.
 *
 * @param value - the data of a data part.
 * @returns True when it names a call, a tool and a list of options.
 */
function isToolResponseRequiredPayload(value: unknown): value is ToolResponseRequiredPayload {
  const isObject = typeof value === "object" && value !== null;
  if (!isObject) {
    return false;
  }

  const candidate: Partial<Record<keyof ToolResponseRequiredPayload, unknown>> = value;
  const hasToolCallId = typeof candidate.toolCallId === "string";
  const hasToolName = typeof candidate.toolName === "string";
  const hasOptions =
    Array.isArray(candidate.options) &&
    candidate.options.every((option) => typeof option === "string");

  return hasToolCallId && hasToolName && hasOptions;
}

/**
 * Read a tool call's arguments as a plain object, or an empty one when they are not.
 *
 * @param input - the tool part's input as the stream delivered it.
 * @returns The arguments to show.
 */
function argumentsFrom(input: unknown): Record<string, unknown> {
  const isObject = typeof input === "object" && input !== null && !Array.isArray(input);
  if (!isObject) {
    return {};
  }

  const toolArguments: Record<string, unknown> = { ...input };

  return toolArguments;
}

/**
 * Return the call the newest assistant message is waiting on, or null.
 *
 * @param messages - the chat's messages, oldest first.
 * @returns The pending call with its options, or null when nothing is pending.
 */
export function pendingToolResponseIn(messages: UIMessage[]): PendingToolResponse | null {
  const newestMessage = messages.at(-1);
  const isAssistantMessage = newestMessage?.role === "assistant";
  if (!isAssistantMessage) {
    return null;
  }

  // Unanswered calls first, so a response-required part whose call has since been
  // answered is ignored.
  const unansweredInputsByCallId = new Map<string, unknown>();
  for (const part of newestMessage.parts) {
    const isUnansweredCall =
      isToolUIPart(part) && part.state === TOOL_PART_STATE_INPUT_AVAILABLE;
    if (isUnansweredCall) {
      unansweredInputsByCallId.set(part.toolCallId, part.input);
    }
  }

  for (const part of newestMessage.parts) {
    const isResponseRequired = part.type === TOOL_RESPONSE_REQUIRED_PART_TYPE;
    if (!isResponseRequired) {
      continue;
    }

    const payload = part.data;
    const isPayload = isToolResponseRequiredPayload(payload);
    if (!isPayload) {
      continue;
    }

    const isStillUnanswered = unansweredInputsByCallId.has(payload.toolCallId);
    if (!isStillUnanswered) {
      continue;
    }

    const input = unansweredInputsByCallId.get(payload.toolCallId);
    const pendingResponse: PendingToolResponse = {
      toolCallId: payload.toolCallId,
      toolName: payload.toolName,
      arguments: argumentsFrom(input),
      options: payload.options,
    };

    return pendingResponse;
  }

  return null;
}
