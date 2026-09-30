/**
 * The login screen: one button per seeded tenant.
 *
 * There is no password; picking a tenant is the claim the backend then checks on every
 * request through the tenant header.
 */

import { useEffect, useState } from "react";
import type { ReactElement } from "react";

import { listTenants } from "../api/client";
import type { TenantSummary } from "../api/types";
import { APPLICATION_TITLE, LOADING_TENANTS_TEXT, LOGIN_PROMPT } from "../constants/ui";

/** What the screen needs: what to do with the chosen tenant. */
export interface TenantLoginProps {
  onLogin: (tenantId: string) => void;
}

/**
 * Render the tenant picker.
 *
 * @param props - the login callback.
 * @returns The screen.
 */
export function TenantLogin(props: TenantLoginProps): ReactElement {
  const { onLogin } = props;
  const [tenants, setTenants] = useState<TenantSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let isStale = false;

    listTenants()
      .then((loadedTenants) => {
        if (!isStale) {
          setTenants(loadedTenants);
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
  }, []);

  let body: ReactElement;
  if (loadError !== null) {
    body = <p className="screen-error">{loadError}</p>;
  } else if (tenants === null) {
    body = <p className="screen-loading">{LOADING_TENANTS_TEXT}</p>;
  } else {
    const tenantButtons: ReactElement[] = [];
    for (const tenant of tenants) {
      const tenantButton = (
        <button
          key={tenant.id}
          type="button"
          className="login-tenant"
          onClick={(): void => {
            onLogin(tenant.id);
          }}
        >
          {tenant.display_name}
        </button>
      );
      tenantButtons.push(tenantButton);
    }
    body = <div className="login-tenants">{tenantButtons}</div>;
  }

  return (
    <div className="screen login">
      <h1>{APPLICATION_TITLE}</h1>
      <p>{LOGIN_PROMPT}</p>
      {body}
    </div>
  );
}
