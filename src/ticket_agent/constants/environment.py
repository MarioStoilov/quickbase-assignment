"""How settings are located in the environment."""

# Prefix every environment variable of this application carries, so that unrelated
# variables of the same name (HOST, PORT) do not leak in.
ENVIRONMENT_PREFIX = "TICKET_AGENT_"

# Name of the optional file with variable assignments, read from the working directory.
ENVIRONMENT_FILE_NAME = ".env"
