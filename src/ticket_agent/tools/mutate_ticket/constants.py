"""Constants of the `mutate_ticket` tool."""

# Name the model calls the tool by.
MUTATE_TICKET_TOOL_NAME = "mutate_ticket"

# Argument key naming the ticket the call acts on.
TICKET_ID_ARGUMENT = "ticket_id"

# Argument key naming what the call does, one of the actions below.
ACTION_ARGUMENT = "action"

# Argument key holding the column-to-value mapping of an update.
FIELDS_ARGUMENT = "fields"

# Value of the action argument that changes a ticket's fields.
ACTION_UPDATE = "update"

# Value of the action argument that removes a ticket.
ACTION_DELETE = "delete"

# Every value the action argument may take.
TICKET_ACTIONS = (ACTION_UPDATE, ACTION_DELETE)

# Option the person picks to let the change run.
RESPONSE_OPTION_APPROVE = "approve"

# Option the person picks to refuse the change; nothing is executed.
RESPONSE_OPTION_REJECT = "reject"

# The options every call offers the person, in the order a UI shows them.
MUTATE_RESPONSE_OPTIONS = (RESPONSE_OPTION_APPROVE, RESPONSE_OPTION_REJECT)

# Result text when the person refuses; the model reports this and stops.
REJECTED_BY_USER_RESULT = "the person declined this action; it was not performed"

# Key of the result field saying whether the change was carried out.
PERFORMED_RESULT_KEY = "performed"

# Key of the result field with a sentence describing what happened.
DETAIL_RESULT_KEY = "detail"
