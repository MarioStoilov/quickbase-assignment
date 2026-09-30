/**
 * The application root: the login screen until a tenant is chosen, then the
 * conversation screen for that tenant.
 */

import type { ReactElement } from "react";

import { ConversationScreen } from "./conversation/ConversationScreen";
import { TenantLogin } from "./login/TenantLogin";
import { useSession } from "./session/useSession";

/**
 * Render the screen the session calls for.
 *
 * @returns The login screen or the conversation screen.
 */
export function App(): ReactElement {
  const session = useSession();
  const tenantId = session.tenantId;
  const isLoggedIn = tenantId !== null;

  if (!isLoggedIn) {
    return <TenantLogin onLogin={session.login} />;
  }

  return (
    <ConversationScreen
      tenantId={tenantId}
      conversationId={session.conversationId}
      onOpenConversation={session.openConversation}
      onCloseConversation={session.closeConversation}
      onLogout={session.logout}
    />
  );
}
