"""Allowed values and limits of the ticket store."""

from collections.abc import Mapping

# Values a ticket's `status` column may hold, in lifecycle order.
TICKET_STATUSES = ("open", "in_progress", "closed")

# Values a ticket's `priority` column may hold, from least to most urgent.
TICKET_PRIORITIES = ("low", "medium", "high")

# Upper bound on the rows a search returns, so a broad query cannot dump the whole table
# into the model's context.
SEARCH_RESULT_LIMIT = 20

# Columns a caller may change through an update. Everything else (id, tenant, requester,
# timestamps) is fixed once the ticket exists.
MUTABLE_TICKET_FIELDS = frozenset({"title", "description", "status", "priority"})

# Allowed values per constrained mutable column; free-text columns are absent.
ALLOWED_FIELD_VALUES: Mapping[str, tuple[str, ...]] = {
    "status": TICKET_STATUSES,
    "priority": TICKET_PRIORITIES,
}
