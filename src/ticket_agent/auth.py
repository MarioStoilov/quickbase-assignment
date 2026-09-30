"""Where the caller's tenant enters a request.

`TenantAuthMiddleware` runs before routing on every request. For a path under the
protected prefix that is not public it reads the `X-Tenant-ID` header, resolves it to a
tenant row and stores the row in the request state, or answers 401 and never reaches the
router. Handlers receive the stored row through the `CallerTenant` accessor; nothing
downstream reads the header again and nothing takes a tenant id from the model's output.

Note: the header stands in for real authentication, as the brief allows. In production
the middleware would validate a signed token or a session cookie instead and derive the
tenant from that.
"""

from typing import Annotated

from fastapi import Depends, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ticket_agent.constants.auth import (
    PROTECTED_PATH_PREFIX,
    PUBLIC_API_PATHS,
    TENANT_HEADER_NAME,
    TENANT_STATE_KEY,
    UNAUTHORISED_DETAIL,
)
from ticket_agent.db.models import Tenant
from ticket_agent.tenants.repository import TenantRepository


def is_protected_path(path: str) -> bool:
    """Decide whether `path` requires a resolved tenant.

    Args:
        path: the request path without query string.

    Returns:
        True for paths under the protected prefix that are not public.
    """
    is_under_prefix = path.startswith(PROTECTED_PATH_PREFIX)
    is_public = path in PUBLIC_API_PATHS
    is_protected = is_under_prefix and not is_public

    return is_protected


def header_value(scope: Scope, header_name: str) -> str | None:
    """Return the first value of `header_name` from a raw ASGI scope.

    ASGI carries headers as lowercase byte pairs; the name is compared case-insensitively.

    Args:
        scope: the ASGI connection scope.
        header_name: the header to look for, in any case.

    Returns:
        The decoded value, or None when the header is absent.
    """
    wanted_name = header_name.lower().encode("latin-1")

    for raw_name, raw_value in scope["headers"]:
        is_match = raw_name == wanted_name
        if is_match:
            return raw_value.decode("latin-1")

    return None


class TenantAuthMiddleware:
    """ASGI middleware that resolves the tenant on every protected HTTP request.

    Written against the raw ASGI interface rather than `BaseHTTPMiddleware` so that
    streaming responses pass through untouched.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap `app`, the next application in the ASGI chain."""
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Resolve the tenant or reject the request, then hand over to the router.

        Non-HTTP scopes (lifespan) and unprotected paths pass straight through. For a
        protected path a missing or unknown header produces a 401 with one message for
        both cases, so the response does not reveal which tenant slugs exist.

        Args:
            scope: the ASGI connection scope.
            receive: the ASGI receive channel.
            send: the ASGI send channel.
        """
        is_http = scope["type"] == "http"
        if not is_http:
            await self._app(scope, receive, send)
            return

        is_protected = is_protected_path(scope["path"])
        if not is_protected:
            await self._app(scope, receive, send)
            return

        tenant = await self._resolve_tenant(scope)
        is_known_tenant = tenant is not None
        if not is_known_tenant:
            rejection = JSONResponse({"detail": UNAUTHORISED_DETAIL}, status_code=401)
            await rejection(scope, receive, send)
            return

        # `state` is optional in an ASGI scope: uvicorn provides it, an in-process test
        # transport may not, so it is created here when absent.
        request_state = scope.setdefault("state", {})
        request_state[TENANT_STATE_KEY] = tenant
        await self._app(scope, receive, send)

    async def _resolve_tenant(self, scope: Scope) -> Tenant | None:
        """Look up the tenant named by the request's header.

        The lookup uses a session of its own, opened on a worker thread because the
        repository is synchronous; the request's own session does not exist yet.

        Args:
            scope: the ASGI connection scope, carrying the headers and the app state.

        Returns:
            The tenant row, or None when the header is absent, blank or unknown.
        """
        raw_header = header_value(scope, TENANT_HEADER_NAME)
        is_header_present = raw_header is not None and raw_header.strip() != ""
        if not is_header_present:
            return None

        tenant_id = raw_header.strip()
        session_factory = scope["app"].state.session_factory
        tenant = await run_in_threadpool(_lookup_tenant, session_factory, tenant_id)

        return tenant


def _lookup_tenant(session_factory: object, tenant_id: str) -> Tenant | None:
    """Open a short session and fetch the tenant with `tenant_id`.

    Args:
        session_factory: the application's `sessionmaker`.
        tenant_id: the trimmed header value.

    Returns:
        The tenant row, or None.
    """
    with session_factory() as session:  # type: ignore[operator]
        tenant_repository = TenantRepository(session)
        tenant = tenant_repository.get(tenant_id)

    return tenant


def caller_tenant(request: Request) -> Tenant:
    """Return the tenant the middleware stored for this request.

    Args:
        request: the current request.

    Returns:
        The resolved `Tenant` row.

    Raises:
        RuntimeError: the route is outside the protected prefix, so the middleware never
            ran. That is a wiring mistake, not a caller error, hence not a 401.
    """
    tenant = getattr(request.state, TENANT_STATE_KEY, None)
    is_resolved = tenant is not None

    if not is_resolved:
        raise RuntimeError(f"{request.url.path} is not covered by TenantAuthMiddleware")

    return tenant


# Annotation handlers use to receive the resolved tenant with its type.
CallerTenant = Annotated[Tenant, Depends(caller_tenant)]
