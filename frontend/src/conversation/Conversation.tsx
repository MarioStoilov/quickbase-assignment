/**
 * The chat of one tenant conversation: messages, composer, and the tool response
 * dialog when a call waits for the person.
 *
 * This is the one place assistant-ui's thread-named primitives are used; everything
 * built on top speaks of conversations.
 */

import {
  AssistantRuntimeProvider,
  AuiIf,
  ComposerPrimitive,
  ThreadPrimitive,
} from "@assistant-ui/react";
import type { AssistantState } from "@assistant-ui/react";
import type { UIMessage } from "ai";
import { useCallback } from "react";
import type { ReactElement } from "react";

import {
  COMPOSER_BLOCKED_PLACEHOLDER,
  COMPOSER_PLACEHOLDER,
  EMPTY_CONVERSATION_TEXT,
  SEND_BUTTON_LABEL,
} from "../constants/ui";
import { pendingToolResponseIn } from "../tools/pendingToolResponse";
import { ToolResponseModal } from "../tools/ToolResponseModal";
import { AssistantMessage } from "./AssistantMessage";
import { toolResponseBody } from "./ConversationTransport";
import { useConversationRuntime } from "./useConversationRuntime";
import { UserMessage } from "./UserMessage";

/** Which conversation to show and what it starts with. */
export interface ConversationProps {
  tenantId: string;
  conversationId: string;
  initialMessages: UIMessage[];
}

/** What the message list's render function receives: the message being rendered. */
interface MessageRenderContext {
  message: { role: string };
}

/**
 * Pick the component for one message by its role.
 *
 * @param context - the message being rendered.
 * @returns The user or the assistant message component.
 */
function renderMessage(context: MessageRenderContext): ReactElement {
  const isUserMessage = context.message.role === "user";
  if (isUserMessage) {
    return <UserMessage />;
  }

  return <AssistantMessage />;
}

/**
 * Tell whether the conversation has no messages yet.
 *
 * @param state - the assistant-ui state.
 * @returns True before the first message.
 */
function isConversationEmpty(state: AssistantState): boolean {
  const isEmpty = state.thread.isEmpty;

  return isEmpty;
}

/**
 * Render the conversation.
 *
 * While a tool call waits for the person, the composer is disabled and the dialog is
 * shown; the answer is sent through the chat so the continuation streams into the
 * same assistant message.
 *
 * @param props - tenant, conversation id and the messages rebuilt from the backend.
 * @returns The chat.
 */
export function Conversation(props: ConversationProps): ReactElement {
  const { tenantId, conversationId, initialMessages } = props;
  const { runtime, chat } = useConversationRuntime(tenantId, conversationId, initialMessages);

  const pendingToolResponse = pendingToolResponseIn(chat.messages);
  const isBlocked = pendingToolResponse !== null;
  const isBusy = chat.status === "submitted" || chat.status === "streaming";
  const composerPlaceholder = isBlocked ? COMPOSER_BLOCKED_PLACEHOLDER : COMPOSER_PLACEHOLDER;
  const pendingToolCallId = pendingToolResponse?.toolCallId ?? null;

  const respondToToolCall = useCallback(
    (option: string): void => {
      const hasPendingCall = pendingToolCallId !== null;
      if (!hasPendingCall) {
        return;
      }

      const body = toolResponseBody({ toolCallId: pendingToolCallId, option });
      void chat.sendMessage(undefined, { body });
    },
    [chat, pendingToolCallId],
  );

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadPrimitive.Root className="conversation">
        <ThreadPrimitive.Viewport className="conversation-viewport">
          <AuiIf condition={isConversationEmpty}>
            <p className="conversation-empty">{EMPTY_CONVERSATION_TEXT}</p>
          </AuiIf>
          <ThreadPrimitive.Messages>{renderMessage}</ThreadPrimitive.Messages>
        </ThreadPrimitive.Viewport>
        <ComposerPrimitive.Root className="composer">
          <ComposerPrimitive.Input
            className="composer-input"
            placeholder={composerPlaceholder}
            disabled={isBlocked}
          />
          <ComposerPrimitive.Send className="composer-send" disabled={isBlocked}>
            {SEND_BUTTON_LABEL}
          </ComposerPrimitive.Send>
        </ComposerPrimitive.Root>
      </ThreadPrimitive.Root>
      {isBlocked && (
        <ToolResponseModal
          pending={pendingToolResponse}
          isBusy={isBusy}
          onRespond={respondToToolCall}
        />
      )}
    </AssistantRuntimeProvider>
  );
}
