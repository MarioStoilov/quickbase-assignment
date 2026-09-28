"""Talking to the language model behind a provider-neutral interface.

`conversation` and `events` define what the rest of the application exchanges with a
model; `provider` is the protocol; `gemini` is the one implementation and the only
module in the tree that imports the vendor SDK; `factory` builds it from the settings.
"""
