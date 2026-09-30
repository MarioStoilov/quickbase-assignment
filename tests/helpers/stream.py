"""Parse an AI SDK UI message stream body into its parts."""

import json
from dataclasses import dataclass
from typing import Any

from ticket_agent.constants.ui_stream import (
    FIELD_TYPE,
    SSE_DATA_PREFIX,
    STREAM_TERMINATOR,
)


@dataclass(frozen=True)
class ParsedStream:
    """The parts of one streamed response and whether the terminator followed them."""

    parts: list[dict[str, Any]]
    is_terminated: bool

    def types(self) -> list[str]:
        """Return the part types in order.

        Returns:
            One type string per part.
        """
        part_types = []
        for part in self.parts:
            part_types.append(part[FIELD_TYPE])

        return part_types

    def of_type(self, part_type: str) -> list[dict[str, Any]]:
        """Return the parts of one type, in order.

        Args:
            part_type: the type to select.

        Returns:
            The matching parts; empty when there are none.
        """
        matching_parts = []
        for part in self.parts:
            is_match = part[FIELD_TYPE] == part_type
            if is_match:
                matching_parts.append(part)

        return matching_parts

    def text(self) -> str:
        """Join every text fragment of the stream.

        Returns:
            The assistant's visible text as streamed.
        """
        fragments = []
        for part in self.of_type("text-delta"):
            fragments.append(part["delta"])

        joined_text = "".join(fragments)

        return joined_text


def parse_stream(body: str) -> ParsedStream:
    """Split a server-sent-events body into its JSON parts.

    Args:
        body: the whole response text.

    Returns:
        The parts in order and whether `[DONE]` closed the stream.
    """
    parts: list[dict[str, Any]] = []
    is_terminated = False

    for line in body.splitlines():
        is_data_line = line.startswith(SSE_DATA_PREFIX)
        if not is_data_line:
            continue

        payload = line[len(SSE_DATA_PREFIX) :]
        is_terminator = payload == STREAM_TERMINATOR
        if is_terminator:
            is_terminated = True
            continue

        part = json.loads(payload)
        parts.append(part)

    parsed_stream = ParsedStream(parts=parts, is_terminated=is_terminated)

    return parsed_stream
