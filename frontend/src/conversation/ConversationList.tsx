/**
 * The tenant's conversations, newest first, with the button that starts a new one.
 *
 * Clicking a row opens that conversation; the person can then continue it. A frozen
 * conversation is marked, since it waits for an answer before it takes a message.
 */

import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { createConversation, listConversations } from "../api/client";
import type { ConversationSummary } from "../api/types";
import { CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE } from "../constants/api";
import {
  CONVERSATION_WAITING_MARK,
  CONVERSATIONS_HEADING,
  EMPTY_CONVERSATION_PREVIEW,
  LOADING_CONVERSATIONS_TEXT,
  NEW_CONVERSATION_BUTTON_LABEL,
  NO_CONVERSATIONS_TEXT,
} from "../constants/ui";
import { ScreenHeader } from "../layout/ScreenHeader";

/** What the list needs: whose conversations, and what to do when one is chosen. */
export interface ConversationListProps {
  tenantId: string;
  onOpenConversation: (conversationId: string) => void;
  onLogout: () => void;
}

/**
 * Format a conversation's start time for the list.
 *
 * @param createdAt - the ISO timestamp from the backend.
 * @returns The time in the browser's locale.
 */
function formatStartTime(createdAt: string): string {
  const startTime = new Date(createdAt);
  const text = startTime.toLocaleString();

  return text;
}

/**
 * Render the list screen.
 *
 * @param props - the tenant, the open callback and the logout callback.
 * @returns The screen.
 */
export function ConversationList(props: ConversationListProps): ReactElement {
  const { tenantId, onOpenConversation, onLogout } = props;
  const [conversations, setConversations] = useState<ConversationSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    let isStale = false;

    listConversations(tenantId)
      .then((loadedConversations) => {
        if (!isStale) {
          setConversations(loadedConversations);
        }
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        if (!isStale) {
          setLoadError(message);
        }
      });

    return (): void => {
      isStale = true;
    };
  }, [tenantId]);

  const startConversation = (): void => {
    setIsCreating(true);
    createConversation(tenantId)
      .then((created) => {
        onOpenConversation(created.id);
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : String(error);
        setLoadError(message);
        setIsCreating(false);
      });
  };

  let body: ReactElement;
  if (loadError !== null) {
    body = <p className="screen-error">{loadError}</p>;
  } else if (conversations === null) {
    body = <p className="screen-loading">{LOADING_CONVERSATIONS_TEXT}</p>;
  } else if (conversations.length === 0) {
    body = <p className="screen-loading">{NO_CONVERSATIONS_TEXT}</p>;
  } else {
    const rows: ReactElement[] = [];
    for (const conversation of conversations) {
      const hasPreview = conversation.preview !== "";
      const previewText = hasPreview ? conversation.preview : EMPTY_CONVERSATION_PREVIEW;
      const previewClassName = hasPreview
        ? "conversation-row-preview"
        : "conversation-row-preview conversation-row-preview-empty";
      const isWaiting = conversation.status === CONVERSATION_STATUS_AWAITING_TOOL_RESPONSE;
      const startTimeText = formatStartTime(conversation.created_at);

      const row = (
        <li key={conversation.id}>
          <button
            type="button"
            className="conversation-row"
            onClick={(): void => {
              onOpenConversation(conversation.id);
            }}
          >
            <span className={previewClassName}>{previewText}</span>
            <span className="conversation-row-meta">
              <span>{startTimeText}</span>
              {isWaiting && (
                <span className="conversation-row-waiting">{CONVERSATION_WAITING_MARK}</span>
              )}
            </span>
          </button>
        </li>
      );
      rows.push(row);
    }
    body = <ul className="conversation-list">{rows}</ul>;
  }

  const newConversationButton = (
    <button type="button" onClick={startConversation} disabled={isCreating}>
      {NEW_CONVERSATION_BUTTON_LABEL}
    </button>
  );

  return (
    <div className="screen">
      <ScreenHeader tenantId={tenantId} actions={newConversationButton} onLogout={onLogout} />
      <h2 className="conversations-heading">{CONVERSATIONS_HEADING}</h2>
      {body}
    </div>
  );
}
