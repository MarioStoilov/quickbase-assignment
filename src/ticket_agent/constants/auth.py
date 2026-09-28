"""The header-based stand-in for authentication."""

# Name of the request header that stands in for real authentication.
TENANT_HEADER_NAME = "X-Tenant-ID"

# Error text for a missing and for an unknown header alike, so the response does not
# reveal which tenant slugs exist.
UNAUTHORISED_DETAIL = "missing or unknown tenant"
