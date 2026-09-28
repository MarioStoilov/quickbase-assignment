"""The header-based stand-in for authentication."""

# Name of the request header that stands in for real authentication.
TENANT_HEADER_NAME = "X-Tenant-ID"

# Error text for a missing and for an unknown header alike, so the response does not
# reveal which tenant slugs exist.
UNAUTHORISED_DETAIL = "missing or unknown tenant"

# Every path under this prefix requires a resolved tenant unless listed as public. Paths
# outside it (API docs, the frontend bundle) are served to anyone.
PROTECTED_PATH_PREFIX = "/api/"

# API paths any caller may reach without a tenant header: liveness, and the tenant list
# the login screen needs before a tenant has been chosen.
PUBLIC_API_PATHS = frozenset({"/api/health", "/api/tenants"})

# Key under which the middleware stores the resolved tenant in the request state.
TENANT_STATE_KEY = "tenant"
