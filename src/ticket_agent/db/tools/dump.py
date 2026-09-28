"""Print the current tenants and tickets: `python -m ticket_agent.db.tools.dump [--full]`.

A convenience for checking what `init`, `seed` or a chat session did to the database.
Descriptions are shortened unless `--full` is given, because the injection payloads make
some of them long.
"""

import argparse

from sqlalchemy.orm import Session

from ticket_agent.constants.cli import DESCRIPTION_PREVIEW_LENGTH
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.models import Ticket
from ticket_agent.settings import load_settings
from ticket_agent.tenants.repository import TenantRepository
from ticket_agent.tickets.repository import TicketRepository


def preview_of(description: str, show_full: bool) -> str:
    """Return the description on one line, shortened unless `show_full` is set.

    Args:
        description: the ticket's description, possibly multi-line.
        show_full: keep the whole text instead of cutting it.

    Returns:
        The text with newlines replaced by spaces and, when shortened, an ellipsis.
    """
    single_line = " ".join(description.split())
    is_short_enough = len(single_line) <= DESCRIPTION_PREVIEW_LENGTH

    if show_full or is_short_enough:
        return single_line

    cut_text = single_line[:DESCRIPTION_PREVIEW_LENGTH]
    preview = f"{cut_text}..."

    return preview


def print_ticket(ticket: Ticket, show_full: bool) -> None:
    """Print one ticket as an indented block under its tenant.

    Args:
        ticket: the row to print.
        show_full: print the whole description instead of a preview.
    """
    description_text = preview_of(ticket.description, show_full)

    print(f"  #{ticket.id:<4} [{ticket.status}/{ticket.priority}] {ticket.title}")
    print(f"        from {ticket.requester_email}, updated {ticket.updated_at:%Y-%m-%d %H:%M}")
    print(f"        {description_text}")


def print_database_state(session: Session, show_full: bool) -> None:
    """Print every tenant with its tickets, oldest ticket first.

    Args:
        session: session bound to a database whose schema exists.
        show_full: print whole descriptions instead of previews.
    """
    tenant_repository = TenantRepository(session)
    ticket_repository = TicketRepository(session)
    tenants = tenant_repository.list_all()

    for tenant in tenants:
        tickets = ticket_repository.list_for_tenant(tenant.id)
        ticket_count = len(tickets)

        print(f"{tenant.display_name} ({tenant.id}): {ticket_count} tickets")
        for ticket in tickets:
            print_ticket(ticket, show_full)
        print()


def build_argument_parser() -> argparse.ArgumentParser:
    """Define the `--full` flag.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(
        prog="python -m ticket_agent.db.tools.dump",
        description="Print the tenants and tickets in the configured database.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="print whole descriptions instead of shortened previews",
    )

    return parser


def main() -> None:
    """Parse the command line and print the configured database."""
    parser = build_argument_parser()
    arguments = parser.parse_args()
    settings = load_settings()

    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        print_database_state(session, show_full=arguments.full)

    engine.dispose()


if __name__ == "__main__":
    main()
