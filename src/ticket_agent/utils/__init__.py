"""Developer utilities that are not part of the running system.

One sub-package per area: `db` for seed data, state dumps and, later, direct edits; `llm`
for probing the model. The server never imports from here; only the `cli` entry point
does, to seed.
"""
