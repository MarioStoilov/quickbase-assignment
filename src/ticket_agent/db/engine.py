"""SQLAlchemy engine and session factory for the SQLite database."""

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from ticket_agent.settings import Settings


def _enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    """Turn on foreign-key enforcement for one new SQLite connection.

    SQLite ignores foreign keys unless the pragma is set per connection; without it a
    ticket could reference a tenant that does not exist.

    Args:
        dbapi_connection: the raw sqlite3 connection just opened by the pool.
        _connection_record: the pool's record for that connection, unused.
    """
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_database_engine(settings: Settings) -> Engine:
    """Create the engine for the SQLite file named by `settings`.

    The engine does not create the file's schema; that is the job of `make init`.
    Foreign keys are enforced on every connection the engine opens.

    Args:
        settings: the process settings holding the database path.

    Returns:
        A configured SQLAlchemy engine.
    """
    engine = create_engine(settings.database_url)
    event.listen(engine, "connect", _enable_foreign_keys)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build the factory that request handlers and commands use to open sessions.

    Sessions do not expire loaded objects on commit, so a ticket returned by a
    repository method stays readable after the transaction closes.

    Args:
        engine: the engine the sessions bind to.

    Returns:
        A `sessionmaker` producing one `Session` per call.
    """
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    return session_factory
