"""The pure helpers of the tenant middleware."""

import pytest
from fastapi import Request

from ticket_agent.auth import caller_tenant, header_value, is_protected_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/tickets", True),
        ("/api/chat/new", True),
        ("/api/health", False),
        ("/api/tenants", False),
        ("/docs", False),
        ("/", False),
    ],
)
def test_protected_paths_are_the_api_minus_the_public_ones(path: str, expected: bool) -> None:
    """Everything under /api needs a tenant except health and the tenant list."""
    assert is_protected_path(path) is expected


def test_header_value_is_case_insensitive() -> None:
    """The header is found whatever case the name is asked for in."""
    scope = {"headers": [(b"x-tenant-id", b"acme"), (b"accept", b"*/*")]}

    assert header_value(scope, "X-Tenant-ID") == "acme"


def test_header_value_is_none_when_absent() -> None:
    """A header that is not present yields None rather than an error."""
    scope = {"headers": [(b"accept", b"*/*")]}

    assert header_value(scope, "Authorization") is None


def test_caller_tenant_outside_the_middleware_is_a_wiring_error() -> None:
    """A route the middleware never covered raises, rather than answering 401."""
    scope = {"type": "http", "path": "/outside", "headers": [], "state": {}, "query_string": b""}
    request = Request(scope)

    with pytest.raises(RuntimeError, match="not covered"):
        caller_tenant(request)
