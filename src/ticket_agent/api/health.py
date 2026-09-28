"""Liveness endpoint."""

from fastapi import APIRouter
from pydantic import BaseModel

from ticket_agent import __version__

router = APIRouter()


class HealthResponse(BaseModel):
    """Body of the health endpoint."""

    status: str
    version: str


@router.get("/api/health")
def read_health() -> HealthResponse:
    """Report that the server is up and which version it runs.

    Returns:
        Status `ok` and the package version.
    """
    response = HealthResponse(status="ok", version=__version__)

    return response
