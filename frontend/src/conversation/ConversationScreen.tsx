/**
 * The chat screen: header with the way back to the list, and one conversation read
 * back from the backend before it is shown.
 */

import type { UIMessage } from "ai";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { ApiError, readConversation } from "../api/client";
import { NOT_FOUND_STATUS } from "../constants/api";
import { CONVERSATIONS_BUTTON_LABEL, LOADING_CONVERSATION_TEXT } from "../constants/ui";
import { ScreenHeader } from "../layout/ScreenHeader";
import { Conversation } from "./Conversation";
import { uiMessagesFromConversation } from "./storedMessages";

/** The session values and actions the screen works with. */
export interface ConversationScreenProps {
  tenantId: string;
  conversationId: string;
  onCloseConversation: () => void;
  onLogout: () => void;
}

/** A conversation read from the backend, ready to render. */
interface LoadedConversation {
  conversationId: string;
  initialMessages: UIMessage[];
}

/** A failure to read a conversation, kept with the id it happened for. */
interface LoadFailure {
  conversationId: string;
  message: string;
}

/**
 * Render the header and the conversation.
 *
 * The conversation is read back first so the chat starts with its history and, when
 * it is frozen, the dialog. A 404, which the backend answers for an unknown or
 * foreign id, closes the conversation so the person lands on the list. Loaded and
 * failed states remember the id they belong to, so a change of conversation shows
 * the loading text without any state being reset.
 *
 * @param props - the session values and the actions that change them.
 * @returns The screen.
 */
export function ConversationScreen(props: ConversationScreenProps): ReactElement {
  const { tenantId, conversationId, onCloseConversation, onLogout } = props;
  const [loaded, setLoaded] = useState<LoadedConversation | null>(null);
  const [failure, setFailure] = useState<LoadFailure | null>(null);

  useEffect(() => {
    let isStale = false;

    readConversation(tenantId, conversationId)
      .then((conversation) => {
        const initialMessages = uiMessagesFromConversation(conversation);
        if (!isStale) {
          setLoaded({ conversationId, initialMessages });
        }
      })
      .catch((error: unknown) => {
        if (isStale) {
          return;
        }
        const isStaleId = error instanceof ApiError && error.status === NOT_FOUND_STATUS;
        if (isStaleId) {
          onCloseConversation();
          return;
        }
        const message = error instanceof Error ? error.message : String(error);
        setFailure({ conversationId, message });
      });

    return (): void => {
      isStale = true;
    };
  }, [tenantId, conversationId, onCloseConversation]);

  const isLoaded = loaded !== null && loaded.conversationId === conversationId;
  const isFailed = failure !== null && failure.conversationId === conversationId;

  let body: ReactElement;
  if (isFailed) {
    body = <p className="screen-error">{failure.message}</p>;
  } else if (isLoaded) {
    body = (
      <Conversation
        key={loaded.conversationId}
        tenantId={tenantId}
        conversationId={loaded.conversationId}
        initialMessages={loaded.initialMessages}
      />
    );
  } else {
    body = <p className="screen-loading">{LOADING_CONVERSATION_TEXT}</p>;
  }

  const conversationsButton = (
    <button type="button" onClick={onCloseConversation}>
      {CONVERSATIONS_BUTTON_LABEL}
    </button>
  );

  return (
    <div className="screen">
      <ScreenHeader tenantId={tenantId} actions={conversationsButton} onLogout={onLogout} />
      {body}
    </div>
  );
}
