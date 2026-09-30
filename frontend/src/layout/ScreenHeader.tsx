/**
 * The header shared by the screens after login: title, the tenant acted as, and the
 * screen's action buttons with "Log out" last.
 */

import type { ReactElement, ReactNode } from "react";

import { ACTING_AS_PREFIX, APPLICATION_TITLE, LOGOUT_BUTTON_LABEL } from "../constants/ui";

/** What the header shows: the tenant, the screen's own buttons, the logout action. */
export interface ScreenHeaderProps {
  tenantId: string;
  actions: ReactNode;
  onLogout: () => void;
}

/**
 * Render the header.
 *
 * @param props - the tenant, the screen's buttons and the logout callback.
 * @returns The header.
 */
export function ScreenHeader(props: ScreenHeaderProps): ReactElement {
  const { tenantId, actions, onLogout } = props;

  return (
    <header className="screen-header">
      <h1>{APPLICATION_TITLE}</h1>
      <p className="screen-tenant">
        {ACTING_AS_PREFIX} <strong>{tenantId}</strong>
      </p>
      <div className="screen-actions">
        {actions}
        <button type="button" onClick={onLogout}>
          {LOGOUT_BUTTON_LABEL}
        </button>
      </div>
    </header>
  );
}
