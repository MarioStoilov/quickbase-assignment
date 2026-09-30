"""Facts about the tools that tests assert against or call them with."""

# The tools the application registers, in registration order.
DEFAULT_TOOL_NAMES = ["search_tickets", "mutate_ticket", "create_ticket"]

# A complete, valid create_ticket proposal.
VALID_CREATE_ARGUMENTS = {
    "title": "Printer jams",
    "description": "The floor 3 printer jams every morning.",
    "requester_email": "pat.okafor@acme.example",
}
