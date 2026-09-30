/**
 * Wire one conversation's transport into the AI SDK chat and hand it to assistant-ui.
 */

import { useChat } from "@ai-sdk/react";
import type { UseChatHelpers } from "@ai-sdk/react";
import type { AssistantRuntime } from "@assistant-ui/react";
import { useAISDKRuntime } from "@assistant-ui/react-ai-sdk";
import type { UIMessage } from "ai";
import { useMemo } from "react";

import { ConversationTransport } from "./ConversationTransport";

/** The assistant-ui runtime of a conversation and the AI SDK chat underneath it. */
export interface ConversationRuntime {
  runtime: AssistantRuntime;
  chat: UseChatHelpers<UIMessage>;
}

/**
 * Create the chat and runtime of one conversation.
 *
 * The chat is keyed by the conversation id, so a different conversation gets a fresh
 * chat with its own messages. Pending tool calls are never cancelled by sending a
 * message, because the composer is blocked while one is pending and the backend would
 * refuse the message anyway.
 *
 * @param tenantId - the tenant every request is sent for.
 * @param conversationId - the conversation every request addresses.
 * @param initialMessages - the messages rebuilt from the backend, empty for a new one.
 * @returns The runtime for the assistant-ui provider and the chat for the modal.
 */
export function useConversationRuntime(
  tenantId: string,
  conversationId: string,
  initialMessages: UIMessage[],
): ConversationRuntime {
  const transport = useMemo(
    () => new ConversationTransport(tenantId, conversationId),
    [tenantId, conversationId],
  );
  const chat = useChat({ id: conversationId, transport, messages: initialMessages });
  const runtime = useAISDKRuntime(chat, { cancelPendingToolCallsOnSend: false });

  const conversationRuntime: ConversationRuntime = { runtime, chat };

  return conversationRuntime;
}
