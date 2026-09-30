"""The `init` and `seed` commands against a temporary database file."""

from pathlib import Path

import pytest
from sqlalchemy import Engine

from ticket_agent import cli
from ticket_agent.constants.cli import EXIT_CODE_REFUSED
from ticket_agent.constants.seed import ACME_TENANT_ID
from ticket_agent.db.engine import create_database_engine, create_session_factory
from ticket_agent.db.schema import create_schema, schema_exists
from ticket_agent.settings import Settings
from ticket_agent.tickets.repository import TicketRepository
from ticket_agent.utils.db.seed_data import SEED_TENANTS, SEED_TICKETS


@pytest.fixture
def empty_engine(settings: Settings) -> Engine:
    """An engine on the test database with no schema yet."""
    engine = create_database_engine(settings)

    return engine


def ticket_count_of(engine: Engine) -> int:
    """Count the tickets in the database behind `engine`.

    Args:
        engine: the engine to count through.

    Returns:
        The row count.
    """
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        count = cli.count_tickets(session)

    return count


def test_init_creates_the_schema_and_seeds_it(
    empty_engine: Engine, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fresh file gets every table and the seed rows, and the command reports counts."""
    cli.run_init(empty_engine, settings, reset=False)

    assert schema_exists(empty_engine)
    assert ticket_count_of(empty_engine) == len(SEED_TICKETS)
    output = capsys.readouterr().out
    assert f"seeded {len(SEED_TENANTS)} tenants and {len(SEED_TICKETS)} tickets" in output


def test_init_refuses_an_existing_schema_without_reset(
    empty_engine: Engine, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """A second init without --reset exits with the refusal code and touches nothing."""
    cli.run_init(empty_engine, settings, reset=False)

    with pytest.raises(SystemExit) as exit_info:
        cli.run_init(empty_engine, settings, reset=False)

    assert exit_info.value.code == EXIT_CODE_REFUSED
    assert "already has a schema" in capsys.readouterr().err
    assert ticket_count_of(empty_engine) == len(SEED_TICKETS)


def test_init_with_reset_drops_and_reseeds(empty_engine: Engine, settings: Settings) -> None:
    """After changes, init --reset returns the database to the seed state."""
    cli.run_init(empty_engine, settings, reset=False)
    session_factory = create_session_factory(empty_engine)
    with session_factory() as session:
        TicketRepository(session).create(
            ACME_TENANT_ID, "Extra", "Added after the seed.", "low", "extra@acme.example"
        )
    assert ticket_count_of(empty_engine) == len(SEED_TICKETS) + 1

    cli.run_init(empty_engine, settings, reset=True)

    assert ticket_count_of(empty_engine) == len(SEED_TICKETS)


def test_seed_refuses_a_missing_schema_and_a_seeded_database(
    empty_engine: Engine, settings: Settings, capsys: pytest.CaptureFixture[str]
) -> None:
    """seed needs the schema and refuses to double the data."""
    with pytest.raises(SystemExit):
        cli.run_seed(empty_engine, settings)
    assert "has no schema" in capsys.readouterr().err

    create_schema(empty_engine)
    cli.run_seed(empty_engine, settings)
    with pytest.raises(SystemExit):
        cli.run_seed(empty_engine, settings)
    assert "already holds" in capsys.readouterr().err


def test_count_tickets_is_zero_on_an_empty_schema(empty_engine: Engine) -> None:
    """An empty tickets table counts as zero, not None."""
    create_schema(empty_engine)
    assert ticket_count_of(empty_engine) == 0


def test_main_runs_init_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The entry point reads the settings, creates the parent directory and runs init."""
    database_path = tmp_path / "nested" / "cli.db"
    monkeypatch.setenv("TICKET_AGENT_DATABASE_PATH", str(database_path))
    monkeypatch.setattr("sys.argv", ["ticket_agent.cli", "init"])

    cli.main()

    assert database_path.exists()
    assert "created schema" in capsys.readouterr().out


def test_main_runs_seed_from_the_command_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The seed subcommand loads data into a schema created beforehand."""
    database_path = tmp_path / "seed.db"
    monkeypatch.setenv("TICKET_AGENT_DATABASE_PATH", str(database_path))
    create_schema(create_database_engine(Settings(database_path=database_path)))
    monkeypatch.setattr("sys.argv", ["ticket_agent.cli", "seed"])

    cli.main()

    assert "seeded" in capsys.readouterr().out
