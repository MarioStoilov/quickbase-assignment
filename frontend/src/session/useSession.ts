/**
 * The browser session: which tenant the person acts as and which conversation is open.
 *
 * Both values live in `sessionStorage`, so a reload keeps the chat and a new tab starts
 * at the login screen. The tenant id is sent with every request as the tenant header;
 * it is the client's claim, which the backend resolves or refuses.
 */

import { useCallback, useState } from "react";

import { SESSION_STORAGE_CONVERSATION_KEY, SESSION_STORAGE_TENANT_KEY } from "../constants/api";

/** What the session holds and the actions that change it. */
export interface Session {
  tenantId: string | null;
  conversationId: string | null;
  login: (tenantId: string) => void;
  logout: () => void;
  openConversation: (conversationId: string) => void;
  closeConversation: () => void;
}

/**
 * Read one stored value, or null when the key is absent.
 *
 * @param key - the storage key.
 * @returns The stored string or null.
 */
function readStoredValue(key: string): string | null {
  const storedValue = window.sessionStorage.getItem(key);

  return storedValue;
}

/**
 * Store one value, or remove the key when the value is null.
 *
 * @param key - the storage key.
 * @param value - the value to keep, or null to forget it.
 */
function writeStoredValue(key: string, value: string | null): void {
  const isForgetting = value === null;

  if (isForgetting) {
    window.sessionStorage.removeItem(key);
  } else {
    window.sessionStorage.setItem(key, value);
  }
}

/**
 * Hold the tenant and conversation of this browser session, backed by sessionStorage.
 *
 * Logging out also closes the conversation, since a conversation belongs to a tenant.
 *
 * @returns The session values and the actions that change them.
 */
export function useSession(): Session {
  const [tenantId, setTenantId] = useState<string | null>(() =>
    readStoredValue(SESSION_STORAGE_TENANT_KEY),
  );
  const [conversationId, setConversationId] = useState<string | null>(() =>
    readStoredValue(SESSION_STORAGE_CONVERSATION_KEY),
  );

  const login = useCallback((chosenTenantId: string): void => {
    writeStoredValue(SESSION_STORAGE_TENANT_KEY, chosenTenantId);
    setTenantId(chosenTenantId);
  }, []);

  const logout = useCallback((): void => {
    writeStoredValue(SESSION_STORAGE_CONVERSATION_KEY, null);
    writeStoredValue(SESSION_STORAGE_TENANT_KEY, null);
    setConversationId(null);
    setTenantId(null);
  }, []);

  const openConversation = useCallback((openedConversationId: string): void => {
    writeStoredValue(SESSION_STORAGE_CONVERSATION_KEY, openedConversationId);
    setConversationId(openedConversationId);
  }, []);

  const closeConversation = useCallback((): void => {
    writeStoredValue(SESSION_STORAGE_CONVERSATION_KEY, null);
    setConversationId(null);
  }, []);

  const session: Session = {
    tenantId,
    conversationId,
    login,
    logout,
    openConversation,
    closeConversation,
  };

  return session;
}
