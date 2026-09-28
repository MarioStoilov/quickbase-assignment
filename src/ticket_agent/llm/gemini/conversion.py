"""Turn the provider-neutral history and declarations into Gemini SDK request types."""

from collections.abc import Sequence

from google.genai import types

from ticket_agent.llm.conversation import (
    AssistantMessage,
    Message,
    ToolDeclaration,
    ToolResultMessage,
    UserMessage,
)
from ticket_agent.llm.gemini.signatures import signature_from_state


def config_for_turn(
    system_prompt: str, tool_declarations: Sequence[ToolDeclaration]
) -> types.GenerateContentConfig:
    """Build the request configuration: prompt, tools, no automatic function calling.

    Args:
        system_prompt: instructions sent as the system instruction.
        tool_declarations: tools to declare; when empty no tool is offered.

    Returns:
        The SDK configuration for one request.
    """
    function_declarations = []
    for declaration in tool_declarations:
        function_declaration = types.FunctionDeclaration(
            name=declaration.name,
            description=declaration.description,
            parameters_json_schema=dict(declaration.parameters_schema),
        )
        function_declarations.append(function_declaration)

    has_tools = len(function_declarations) > 0
    tools: list[types.Tool] | None = None
    if has_tools:
        tools = [types.Tool(function_declarations=function_declarations)]

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    return config


def contents_from_history(history: Sequence[Message]) -> list[types.Content]:
    """Convert the history to the SDK's content list.

    Consecutive tool results are merged into one user content with several function
    response parts, because Gemini expects the responses to one model turn together.

    Args:
        history: the conversation so far, oldest first.

    Returns:
        One `Content` per user or assistant message, one per run of tool results.
    """
    contents: list[types.Content] = []

    for message in history:
        is_tool_result = isinstance(message, ToolResultMessage)
        previous_content = contents[-1] if contents else None
        is_previous_tool_results = previous_content is not None and _holds_function_responses(
            previous_content
        )

        if is_tool_result and is_previous_tool_results:
            response_part = _function_response_part(message)
            previous_content.parts.append(response_part)
            continue

        content = _content_from_message(message)
        contents.append(content)

    return contents


def _holds_function_responses(content: types.Content) -> bool:
    """Report whether `content` is a run of function responses built earlier.

    Args:
        content: an SDK content already in the list.

    Returns:
        True when its first part is a function response.
    """
    has_parts = content.parts is not None and len(content.parts) > 0
    if not has_parts:
        return False

    first_part = content.parts[0]
    is_function_response = first_part.function_response is not None

    return is_function_response


def _content_from_message(message: Message) -> types.Content:
    """Convert one history message to an SDK content.

    Args:
        message: a user, assistant or tool-result message.

    Returns:
        The content with the role Gemini expects for that message kind.
    """
    if isinstance(message, UserMessage):
        text_part = types.Part.from_text(text=message.text)
        content = types.Content(role="user", parts=[text_part])
        return content

    if isinstance(message, AssistantMessage):
        parts: list[types.Part] = []
        has_text = message.text != ""
        if has_text:
            text_signature = signature_from_state(message.provider_state)
            text_part = types.Part(text=message.text, thought_signature=text_signature)
            parts.append(text_part)
        for tool_call in message.tool_calls:
            function_call = types.FunctionCall(
                id=tool_call.call_id, name=tool_call.tool_name, args=dict(tool_call.arguments)
            )
            call_signature = signature_from_state(tool_call.provider_state)
            call_part = types.Part(function_call=function_call, thought_signature=call_signature)
            parts.append(call_part)
        content = types.Content(role="model", parts=parts)
        return content

    response_part = _function_response_part(message)
    content = types.Content(role="user", parts=[response_part])

    return content


def _function_response_part(message: ToolResultMessage) -> types.Part:
    """Wrap one tool result as a function response part.

    Args:
        message: the tool result to hand back.

    Returns:
        The SDK part carrying the call id, tool name and result mapping.
    """
    function_response = types.FunctionResponse(
        id=message.call_id, name=message.tool_name, response=dict(message.result)
    )
    part = types.Part(function_response=function_response)

    return part
