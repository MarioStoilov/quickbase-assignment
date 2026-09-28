"""Send one message to the configured model and stream the reply to the terminal:
`python -m ticket_agent.utils.llm.probe <words of the message>`.

A developer check that the key, the model id and the adapter work, independent of the
chat endpoint. The system prompt is the real one; no tools are declared.
"""

import argparse
import asyncio
import sys

from ticket_agent.constants.system_prompt import SYSTEM_PROMPT
from ticket_agent.llm.conversation import UserMessage
from ticket_agent.llm.events import TextDelta, ToolCallRequest, TurnFinished
from ticket_agent.llm.factory import ModelNotConfigured, build_model_provider
from ticket_agent.llm.provider import ModelProvider, ModelProviderError
from ticket_agent.settings import load_settings


async def stream_reply(provider: ModelProvider, message_text: str) -> None:
    """Send `message_text` as the only user message and print the events as they come.

    Args:
        provider: the model to talk to.
        message_text: what the user says.

    Raises:
        ModelProviderError: the model request failed.
    """
    history = [UserMessage(text=message_text)]

    async for event in provider.stream_turn(SYSTEM_PROMPT, history, tool_declarations=[]):
        if isinstance(event, TextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, ToolCallRequest):
            print(f"\n[tool call {event.call_id}: {event.tool_name} {dict(event.arguments)}]")
        elif isinstance(event, TurnFinished):
            detail_suffix = f" ({event.detail})" if event.detail else ""
            print(f"\n[finished: {event.reason}{detail_suffix}]")


def build_argument_parser() -> argparse.ArgumentParser:
    """Define the positional message words.

    Returns:
        The parser; `words` holds the message split by the shell.
    """
    parser = argparse.ArgumentParser(
        prog="python -m ticket_agent.utils.llm.probe",
        description="Send one message to the configured Gemini model and stream the reply.",
    )
    parser.add_argument("words", nargs="+", help="the message to send")

    return parser


def main() -> None:
    """Parse the message, build the provider and stream one reply."""
    parser = build_argument_parser()
    arguments = parser.parse_args()
    message_text = " ".join(arguments.words)
    settings = load_settings()

    try:
        provider = build_model_provider(settings)
        asyncio.run(stream_reply(provider, message_text))
    except (ModelNotConfigured, ModelProviderError) as error:
        # A failure inside the stream arrives after partial text without a newline;
        # end that line so the error does not run into the answer.
        print(flush=True)
        print(f"error: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
