/**
 * The application root: the login screen until a tenant is chosen, then the list of
 * that tenant's conversations, then the chat of the one that is open.
 */

import type { ReactElement } from "react";

import { ConversationList } from "./conversation/ConversationList";
import { ConversationScreen } from "./conversation/ConversationScreen";
import { TenantLogin } from "./login/TenantLogin";
import { useSession } from "./session/useSession";

/**
 * Render the screen the session calls for.
 *
 * @returns The login screen, the conversation list, or the chat.
 */
export function App(): ReactElement {
  const session = useSession();
  const tenantId = session.tenantId;
  const conversationId = session.conversationId;
  const isLoggedIn = tenantId !== null;

  if (!isLoggedIn) {
    return <TenantLogin onLogin={session.login} />;
  }

  const hasOpenConversation = conversationId !== null;
  if (!hasOpenConversation) {
    return (
      <ConversationList
        tenantId={tenantId}
        onOpenConversation={session.openConversation}
        onLogout={session.logout}
      />
    );
  }

  return (
    <ConversationScreen
      tenantId={tenantId}
      conversationId={conversationId}
      onCloseConversation={session.closeConversation}
      onLogout={session.logout}
    />
  );
}
