"""Constants of the `create_ticket` tool."""

# Name the model calls the tool by.
CREATE_TICKET_TOOL_NAME = "create_ticket"

# Argument key holding the new ticket's title.
TITLE_ARGUMENT = "title"

# Argument key holding the new ticket's description.
DESCRIPTION_ARGUMENT = "description"

# Argument key holding the new ticket's priority; optional, see the default in
# `constants.tickets`.
PRIORITY_ARGUMENT = "priority"

# Argument key holding the address of the person the ticket is for. Required: the
# person chatting has no identity beyond the tenant, so the model must ask for it.
REQUESTER_EMAIL_ARGUMENT = "requester_email"

# Option the person picks to let the ticket be created.
RESPONSE_OPTION_APPROVE = "approve"

# Option the person picks to refuse; nothing is created.
RESPONSE_OPTION_REJECT = "reject"

# The options every call offers the person, in the order a UI shows them.
CREATE_RESPONSE_OPTIONS = (RESPONSE_OPTION_APPROVE, RESPONSE_OPTION_REJECT)

# Result text when the person refuses; the model reports this and stops.
REJECTED_BY_USER_RESULT = "the person declined this action; no ticket was created"

# Key of the result field saying whether the ticket was created.
PERFORMED_RESULT_KEY = "performed"

# Key of the result field holding the new ticket's id.
TICKET_ID_RESULT_KEY = "ticket_id"

# Key of the result field with a sentence describing what happened.
DETAIL_RESULT_KEY = "detail"
