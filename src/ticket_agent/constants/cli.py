"""Database administration commands and how the server refers to them."""

# Process exit code when a command refuses to run because of the database's state.
EXIT_CODE_REFUSED = 1

# Command a reader is pointed at when the database has not been initialised.
INIT_COMMAND_HINT = "make init"
