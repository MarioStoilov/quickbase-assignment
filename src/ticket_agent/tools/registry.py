"""The set of tools the model may request in this application."""

from ticket_agent.constants.tools import UNKNOWN_TOOL_ERROR
from ticket_agent.llm.conversation import ToolDeclaration
from ticket_agent.tools.base import Tool, ToolError


class ToolRegistry:
    """The tools offered to the model, looked up by the name the model uses.

    The agent loop sees only this object, so adding a tool changes no code in the loop.
    """

    def __init__(self) -> None:
        """Create an empty registry."""
        self._tools_by_name: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Add `tool` under its own name.

        Args:
            tool: the tool to offer the model.

        Raises:
            ValueError: a tool with that name is already registered, which would make
                one of them unreachable.
        """
        is_taken = tool.name in self._tools_by_name

        if is_taken:
            raise ValueError(f"a tool named '{tool.name}' is already registered")

        self._tools_by_name[tool.name] = tool

    def get(self, tool_name: str) -> Tool:
        """Return the tool the model asked for.

        Args:
            tool_name: the name from the model's call, which may be anything.

        Returns:
            The registered tool.

        Raises:
            ToolError: no tool of that name is registered; the message is meant for the
                model, which usually corrects itself on the next turn.
        """
        tool = self._tools_by_name.get(tool_name)
        is_known = tool is not None

        if not is_known:
            raise ToolError(f"{UNKNOWN_TOOL_ERROR}: {tool_name}")

        return tool

    def declarations(self) -> list[ToolDeclaration]:
        """Describe every registered tool to the model, in registration order.

        Returns:
            One declaration per tool; empty when nothing is registered.
        """
        declarations = []
        for tool in self._tools_by_name.values():
            declaration = tool.declaration()
            declarations.append(declaration)

        return declarations
