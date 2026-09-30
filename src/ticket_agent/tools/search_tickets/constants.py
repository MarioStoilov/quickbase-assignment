"""Constants of the `search_tickets` tool."""

# Name the model calls the tool by.
SEARCH_TICKETS_TOOL_NAME = "search_tickets"

# Argument key of the free-text query matched against titles and descriptions.
QUERY_ARGUMENT = "query"

# Key of the result list holding one summary per matching ticket.
TICKETS_RESULT_KEY = "tickets"

# Key of the result field holding how many tickets were returned.
COUNT_RESULT_KEY = "count"

# Optional argument key naming one ticket to fetch by id instead of searching by text.
TICKET_ID_ARGUMENT = "ticket_id"
