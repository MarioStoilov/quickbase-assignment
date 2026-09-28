"""Identifiers of the seed data that documentation and tests refer to by name."""

# Slugs of the two seeded tenants; the login screen offers exactly these.
ACME_TENANT_ID = "acme"
GLOBEX_TENANT_ID = "globex"

# The ticket the brief's injection payload tries to exfiltrate. It belongs to Globex, so
# an Acme caller must never see it, whatever the model is told.
TARGET_FOREIGN_TICKET_ID = 47
