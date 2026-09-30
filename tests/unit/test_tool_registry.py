"""`ToolRegistry` and the default registry the application offers the model."""

import pytest

from ticket_agent.constants.tools import UNKNOWN_TOOL_ERROR
from ticket_agent.tools import build_default_registry
from ticket_agent.tools.base import ToolError
from ticket_agent.tools.registry import ToolRegistry
from ticket_agent.tools.search_tickets import SearchTicketsTool

# The tools the application registers, in registration order.
DEFAULT_TOOL_NAMES = ["search_tickets", "mutate_ticket", "create_ticket"]


def test_default_registry_declares_the_three_tools_in_order() -> None:
    """The declarations handed to the model name exactly the registered tools."""
    registry = build_default_registry()

    declaration_names = [declaration.name for declaration in registry.declarations()]

    assert declaration_names == DEFAULT_TOOL_NAMES


def test_declarations_never_contain_a_tenant_or_conversation_field() -> None:
    """No tool schema lets the model name a tenant or a conversation."""
    registry = build_default_registry()

    for declaration in registry.declarations():
        property_names = set(declaration.parameters_schema["properties"].keys())
        assert "tenant_id" not in property_names
        assert "conversation_id" not in property_names


def test_get_of_an_unknown_tool_is_a_tool_error_for_the_model() -> None:
    """A name the model invents is answered with the unknown-tool text, not a crash."""
    registry = build_default_registry()

    with pytest.raises(ToolError) as failure:
        registry.get("drop_database")

    assert str(failure.value).startswith(UNKNOWN_TOOL_ERROR)


def test_registering_the_same_name_twice_is_refused() -> None:
    """Two tools under one name would shadow each other, so the second is rejected."""
    registry = ToolRegistry()
    registry.register(SearchTicketsTool())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(SearchTicketsTool())
