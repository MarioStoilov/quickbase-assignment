"""Gemini adapter: the only package that imports `google.genai`.

`provider` holds the `ModelProvider` implementation; `conversion` turns the neutral
history and declarations into SDK types; `streaming` turns streamed chunks back into
`ModelEvent`s; `signatures` encodes the thought signatures Gemini 3 models require back.
"""

from ticket_agent.llm.gemini.provider import GeminiProvider

__all__ = ["GeminiProvider"]
