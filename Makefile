# Every target runs through uv so the project's locked environment is used.
.PHONY: install lint format init reset-db seed db-dump llm-probe run

# Create the virtual environment and install the locked dependencies.
install:
	uv sync

# Fail if formatting or lint rules are violated; run before reporting a change done.
lint:
	uv run ruff format --check .
	uv run ruff check .

# Apply formatting and the auto-fixable lint rules.
format:
	uv run ruff format .
	uv run ruff check --fix .

# Create the database schema and load the seed data. Refuses an existing schema.
init:
	uv run python -m ticket_agent.cli init

# Drop and recreate the schema, then load the seed data.
reset-db:
	uv run python -m ticket_agent.cli init --reset

# Load the seed data into an existing, empty schema.
seed:
	uv run python -m ticket_agent.cli seed

# Print the tenants and tickets currently in the database (add ARGS=--full for whole
# descriptions).
db-dump:
	uv run python -m ticket_agent.utils.db.dump $(ARGS)

# Send one message to the configured Gemini model and stream the reply, e.g.
# make llm-probe ARGS="what can you do"
llm-probe:
	uv run python -m ticket_agent.utils.llm.probe $(ARGS)

# Start the API server on the configured host and port.
run:
	uv run python -m ticket_agent
