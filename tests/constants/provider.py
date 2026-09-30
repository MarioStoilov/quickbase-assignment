"""Values the scripted provider and the fake Gemini client use."""

# Error raised when the loop calls the model more often than the test scripted; it
# surfaces as a provider error in the stream, which makes the mismatch visible.
OUT_OF_TURNS_MESSAGE = "the scripted provider has no turn left for this call"

# A key that is never sent anywhere: the fake client replaces the real one.
FAKE_API_KEY = "test-key"

# The model id the fake client should be asked for.
FAKE_MODEL_ID = "fake-model"

# A thought signature as the SDK would hand it over.
RAW_SIGNATURE = b"\x00\x01signature"

# Opaque state the fake attaches to a tool call, to check it comes back to the model.
CALL_STATE = {"thought_signature": "call-signature"}

# Opaque state the fake attaches to a finished turn, to check it comes back to the model.
TURN_STATE = {"thought_signature": "turn-signature"}
