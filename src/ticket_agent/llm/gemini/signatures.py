"""Encode and decode the thought signatures Gemini 3 models attach to parts.

The signature is opaque bytes. It is kept as base64 text under `THOUGHT_SIGNATURE_KEY`
in a JSON-compatible `provider_state` mapping so the rest of the application can persist
it and hand it back unchanged.
"""

import base64
from collections.abc import Mapping
from typing import Any

from ticket_agent.constants.llm import THOUGHT_SIGNATURE_KEY


def state_from_signature(thought_signature: bytes | None) -> dict[str, Any]:
    """Encode a signature as JSON-safe provider state.

    Args:
        thought_signature: raw bytes from a part, or None.

    Returns:
        A mapping holding the base64 text under `THOUGHT_SIGNATURE_KEY`, or empty.
    """
    has_signature = thought_signature is not None and len(thought_signature) > 0
    if not has_signature:
        return {}

    encoded_signature = base64.b64encode(thought_signature).decode("ascii")
    state = {THOUGHT_SIGNATURE_KEY: encoded_signature}

    return state


def signature_from_state(provider_state: Mapping[str, Any]) -> bytes | None:
    """Decode the signature stored by `state_from_signature`.

    Args:
        provider_state: the mapping stored on a tool call or assistant message.

    Returns:
        The raw signature bytes, or None when the state holds none.
    """
    encoded_signature = provider_state.get(THOUGHT_SIGNATURE_KEY)
    has_signature = isinstance(encoded_signature, str) and encoded_signature != ""
    if not has_signature:
        return None

    thought_signature = base64.b64decode(encoded_signature)

    return thought_signature
