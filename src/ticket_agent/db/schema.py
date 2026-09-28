"""Create, drop and detect the database schema.

Used by the `init` command and, later, by test fixtures. The API server only checks
that the schema exists; it never creates it.
"""

from sqlalchemy import Engine, inspect

from ticket_agent.db.models import Base


def schema_exists(engine: Engine) -> bool:
    """Report whether every table of the models is present in the database.

    Args:
        engine: engine bound to the database to inspect.

    Returns:
        True when all model tables exist, False when any is missing.
    """
    inspector = inspect(engine)
    existing_table_names = set(inspector.get_table_names())
    expected_table_names = set(Base.metadata.tables.keys())
    is_complete = expected_table_names.issubset(existing_table_names)

    return is_complete


def create_schema(engine: Engine) -> None:
    """Create every table of the models that does not exist yet.

    Args:
        engine: engine bound to the database to create the tables in.
    """
    Base.metadata.create_all(engine)


def drop_schema(engine: Engine) -> None:
    """Drop every table of the models, discarding all data.

    Args:
        engine: engine bound to the database to drop the tables from.
    """
    Base.metadata.drop_all(engine)
