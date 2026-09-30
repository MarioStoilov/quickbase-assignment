"""Facts about the seed data that tests assert against."""

# Acme's seed ticket ids, oldest first.
ACME_TICKET_IDS = [1, 2, 3, 4, 5, 6]

# Globex's seed ticket ids, oldest first; no Acme action may change them.
GLOBEX_TICKET_IDS = [42, 43, 44, 45, 46, 47]

# A ticket id nobody has.
UNKNOWN_TICKET_ID = 999

# A tenant slug that is not seeded.
UNKNOWN_TENANT_ID = "initech"

# Words that appear only in Globex's confidential ticket 47; none may reach Acme.
FOREIGN_SECRET_FRAGMENTS = ["merger data room", "Lee Marchetti", "legal@globex.example"]
