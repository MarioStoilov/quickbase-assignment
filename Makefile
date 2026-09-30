# Every backend target runs through uv so the project's locked environment is used;
# every frontend target runs npm inside `frontend/`. The two are separate services.
.PHONY: install lint format test test-live init reset-db seed db-dump llm-probe run run-all frontend frontend-dev frontend-build

# Create the backend virtual environment with the locked dependencies, install the
# frontend's locked dependencies, and point git at the repository's hooks so the unit
# tests run before every commit.
install:
	uv sync
	cd frontend && npm ci
	git config core.hooksPath .githooks

# Fail if formatting or lint rules are violated in either service; run before
# reporting a change done.
lint:
	uv run ruff format --check .
	uv run ruff check .
	cd frontend && npm run lint && npm run typecheck

# Apply formatting and the auto-fixable lint rules in both services.
format:
	uv run ruff format .
	uv run ruff check --fix .
	cd frontend && npm run format

# Run the backend test suite with line coverage; fails below the threshold set in
# pyproject.toml. Needs no network and no API key.
test:
	uv run pytest --cov --cov-report=term-missing

# Run the live adversarial scenarios against the configured Gemini model on a fresh
# temporary database, and write a transcript report under reports/. Needs
# GEMINI_API_KEY and network; deselected from `make test`.
test-live:
	uv run pytest tests/adversarial -m live_model -p no:cacheprovider

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

# Start both services from one terminal: the backend in the background, then the
# frontend in the foreground. Ctrl+C stops the frontend, and the trap stops the
# backend; the two stay separate processes on their own ports.
run-all:
	@uv run python -m ticket_agent & backend_pid=$$!; \
	trap 'kill $$backend_pid 2>/dev/null' EXIT; \
	cd frontend && npm run build && npm run serve

# Build the frontend and serve the bundle as its own service; API calls are forwarded
# to the running backend. This is the command a reviewer uses next to `make run`.
frontend:
	cd frontend && npm run build && npm run serve

# Serve the frontend from source with hot reload, for working on it.
frontend-dev:
	cd frontend && npm run dev

# Build the frontend bundle into frontend/dist without serving it.
frontend-build:
	cd frontend && npm run build
