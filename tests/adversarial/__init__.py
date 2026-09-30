"""Live adversarial scenarios: real prompt-injection questions to the configured model.

Deselected by default; `make test-live` runs them. Each scenario drives the whole
application with the real Gemini provider on a fresh temporary database, records the
conversation, and a transcript report is written when the run ends.
"""
