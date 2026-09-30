"""The tools the model may request, and the registry the agent loop consults.

`build_default_registry` is the one place where a tool becomes available to the model.
Adding a tool later means one sub-package (its tool class plus its own constants) and
one `register` call here.
"""

from ticket_agent.tools.base import Tool, ToolContext, ToolError
from ticket_agent.tools.create_ticket import CreateTicketTool
from ticket_agent.tools.mutate_ticket import MutateTicketTool
from ticket_agent.tools.registry import ToolRegistry
from ticket_agent.tools.search_tickets import SearchTicketsTool

__all__ = [
    "CreateTicketTool",
    "MutateTicketTool",
    "SearchTicketsTool",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "build_default_registry",
]


def build_default_registry() -> ToolRegistry:
    """Create the registry holding every tool this application offers the model.

    Returns:
        A registry with `search_tickets`, `mutate_ticket` and `create_ticket` registered.
    """
    registry = ToolRegistry()

    registry.register(SearchTicketsTool())
    registry.register(MutateTicketTool())
    registry.register(CreateTicketTool())

    return registry
