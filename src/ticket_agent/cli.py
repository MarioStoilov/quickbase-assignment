"""Database administration commands: `python -m ticket_agent.cli {init,seed}`.

`init` creates the schema and then loads the seed data; `seed` loads the seed data into
an existing, empty schema. The API server never does either, so the database a reviewer
runs against is exactly what these commands produced.
"""

import argparse
import sys
from typing import NoReturn

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from ticket_agent.constants.application import APPLICATION_DESCRIPTION
from ticket_agent.constants.cli import EXIT_CODE_REFUSED
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.models import Tenant, Ticket
from ticket_agent.db.schema import create_schema, drop_schema, schema_exists
from ticket_agent.settings import Settings, load_settings
from ticket_agent.utils.db.seed_data import SEED_TENANTS, SEED_TICKETS


def fail(message: str) -> NoReturn:
    """Print `message` to stderr and exit with the refusal code.

    Args:
        message: what was refused and what to do instead.
    """
    print(f"error: {message}", file=sys.stderr)
    sys.exit(EXIT_CODE_REFUSED)


def seed_database(session: Session) -> tuple[int, int]:
    """Insert the seed tenants and tickets in one transaction.

    Args:
        session: session bound to a database whose schema exists and holds no tickets.

    Returns:
        The number of tenants and the number of tickets inserted.
    """
    for seed_tenant in SEED_TENANTS:
        tenant = Tenant(id=seed_tenant.id, display_name=seed_tenant.display_name)
        session.add(tenant)

    for seed_ticket in SEED_TICKETS:
        ticket = Ticket(
            id=seed_ticket.id,
            tenant_id=seed_ticket.tenant_id,
            title=seed_ticket.title,
            description=seed_ticket.description,
            status=seed_ticket.status,
            priority=seed_ticket.priority,
            requester_email=seed_ticket.requester_email,
        )
        session.add(ticket)

    session.commit()

    tenant_count = len(SEED_TENANTS)
    ticket_count = len(SEED_TICKETS)

    return tenant_count, ticket_count


def count_tickets(session: Session) -> int:
    """Return how many tickets the database holds across all tenants.

    Args:
        session: session bound to a database whose schema exists.

    Returns:
        The row count of the tickets table.
    """
    statement = select(func.count()).select_from(Ticket)
    ticket_count = session.scalar(statement)
    is_count_missing = ticket_count is None

    if is_count_missing:
        return 0

    return ticket_count


def run_seed(engine: Engine, settings: Settings) -> None:
    """Load the seed data into an existing, empty schema and report what was inserted.

    Args:
        engine: engine bound to the configured database.
        settings: process settings, for the path shown in messages.

    Raises:
        SystemExit: the schema is missing, or tickets are already present.
    """
    is_initialised = schema_exists(engine)
    if not is_initialised:
        fail(f"database {settings.database_path} has no schema; run `init` first")

    session_factory = create_session_factory(engine)

    with session_factory() as session:
        existing_ticket_count = count_tickets(session)
        has_tickets = existing_ticket_count > 0
        if has_tickets:
            fail(
                f"database {settings.database_path} already holds {existing_ticket_count} "
                "tickets; use `init --reset` to start over"
            )

        tenant_count, ticket_count = seed_database(session)

    print(f"seeded {tenant_count} tenants and {ticket_count} tickets into {settings.database_path}")


def run_init(engine: Engine, settings: Settings, reset: bool) -> None:
    """Create the schema, dropping an existing one only when `reset` is set, then seed.

    Args:
        engine: engine bound to the configured database.
        settings: process settings, for the path shown in messages.
        reset: drop an existing schema instead of refusing.

    Raises:
        SystemExit: the schema already exists and `reset` is not set.
    """
    is_initialised = schema_exists(engine)

    if is_initialised and not reset:
        fail(
            f"database {settings.database_path} already has a schema; "
            "pass --reset to drop it and start over"
        )

    if is_initialised:
        drop_schema(engine)
        print(f"dropped existing schema in {settings.database_path}")

    create_schema(engine)
    print(f"created schema in {settings.database_path}")

    run_seed(engine, settings)


def build_argument_parser() -> argparse.ArgumentParser:
    """Define the `init` and `seed` subcommands.

    Returns:
        The parser; `command` holds the chosen subcommand.
    """
    parser = argparse.ArgumentParser(
        prog="python -m ticket_agent.cli",
        description=f"{APPLICATION_DESCRIPTION}: database administration.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="create the database schema, then load the seed data"
    )
    init_parser.add_argument(
        "--reset",
        action="store_true",
        help="drop an existing schema and all its data before creating it again",
    )

    subparsers.add_parser("seed", help="load the seed data into an existing, empty schema")

    return parser


def main() -> None:
    """Parse the command line and run the chosen command against the configured database."""
    parser = build_argument_parser()
    arguments = parser.parse_args()
    settings = load_settings()

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_database_engine(settings)

    is_init = arguments.command == "init"
    if is_init:
        run_init(engine, settings, reset=arguments.reset)
    else:
        run_seed(engine, settings)

    engine.dispose()


if __name__ == "__main__":
    main()
