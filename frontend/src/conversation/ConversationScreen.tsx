/**
 * The screen after login: header with the tenant and its actions, and the open
 * conversation, created or read back from the backend first.
 */

import type { UIMessage } from "ai";
import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { ApiError, createConversation, readConversation } from "../api/client";
import { NOT_FOUND_STATUS } from "../constants/api";
import {
  ACTING_AS_PREFIX,
  APPLICATION_TITLE,
  LOADING_CONVERSATION_TEXT,
  LOGOUT_BUTTON_LABEL,
  NEW_CONVERSATION_BUTTON_LABEL,
} from "../constants/ui";
import { Conversation } from "./Conversation";
import { uiMessagesFromConversation } from "./storedMessages";

/** The session values and actions the screen works with. */
export interface ConversationScreenProps {
  tenantId: string;
  conversationId: string | null;
  onOpenConversation: (conversationId: string) => void;
  onCloseConversation: () => void;
  onLogout: () => void;
}

/** A conversation read from the backend, ready to render. */
interface LoadedConversation {
  conversationId: string;
  initialMessages: UIMessage[];
}

/** A failure to create or read a conversation, kept with the id it happened for. */
interface LoadFailure {
  conversationId: string | null;
  message: string;
}

/**
 * Render the header and the conversation.
 *
 * Without a conversation id, one is created and stored in the session. With one, it
 * is read back; a 404, which the backend answers for an unknown or foreign id, drops
 * the stale id so a fresh conversation is created on the next pass. Loaded and failed
 * states remember the id they belong to, so a change of conversation shows the
 * loading text without any state being reset.
 *
 * @param props - the session values and the actions that change them.
 * @returns The screen.
 */
export function ConversationScreen(props: ConversationScreenProps): ReactElement {
  const { tenantId, conversationId, onOpenConversation, onCloseConversation, onLogout } = props;
  const [loaded, setLoaded] = useState<LoadedConversation | null>(null);
  const [failure, setFailure] = useState<LoadFailure | null>(null);

  useEffect(() => {
    let isStale = false;

    async function load(): Promise<void> {
      const needsConversation = conversationId === null;
      if (needsConversation) {
        const created = await createConversation(tenantId);
        if (!isStale) {
          onOpenConversation(created.id);
        }
        return;
      }

      try {
        const conversation = await readConversation(tenantId, conversationId);
        const initialMessages = uiMessagesFromConversation(conversation);
        if (!isStale) {
          setLoaded({ conversationId, initialMessages });
        }
      } catch (error) {
        const isStaleId = error instanceof ApiError && error.status === NOT_FOUND_STATUS;
        if (isStaleId && !isStale) {
          onCloseConversation();
          return;
        }
        throw error;
      }
    }

    load().catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      if (!isStale) {
        setFailure({ conversationId, message });
      }
    });

    return (): void => {
      isStale = true;
    };
  }, [tenantId, conversationId, onOpenConversation, onCloseConversation]);

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

  return (
    <div className="screen">
      <header className="screen-header">
        <h1>{APPLICATION_TITLE}</h1>
        <p className="screen-tenant">
          {ACTING_AS_PREFIX} <strong>{tenantId}</strong>
        </p>
        <div className="screen-actions">
          <button type="button" onClick={onCloseConversation}>
            {NEW_CONVERSATION_BUTTON_LABEL}
          </button>
          <button type="button" onClick={onLogout}>
            {LOGOUT_BUTTON_LABEL}
          </button>
        </div>
      </header>
      {body}
    </div>
  );
}
