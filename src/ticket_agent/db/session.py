"""Per-request database sessions for FastAPI handlers."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    """Open one session for the duration of a request and close it afterwards.

    The session factory is created at startup and stored on the application state.

    Args:
        request: the current request, used to reach the application state.

    Yields:
        A session bound to the application's engine.
    """
    session_factory = request.app.state.session_factory
    session = session_factory()

    try:
        yield session
    finally:
        session.close()


# Annotation handlers and dependencies use to receive the per-request session.
DatabaseSession = Annotated[Session, Depends(get_session)]
