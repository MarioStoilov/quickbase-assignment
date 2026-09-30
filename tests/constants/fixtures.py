"""Values the shared fixtures and the application under test are configured with."""

# Name of the per-test database file inside pytest's temporary directory.
TEST_DATABASE_FILE_NAME = "tickets-test.db"

# Base URL the ASGI transport answers under; never dialled.
TEST_BASE_URL = "http://testserver"

# A round bound small enough to hit with two scripted tool turns.
SMALL_ROUND_BOUND = 2

# Length of the hex form of a UUID, which is what the server generates as an id.
UUID_HEX_LENGTH = 32
