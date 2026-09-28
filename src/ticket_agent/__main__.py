"""Start the API server: `python -m ticket_agent`."""

import uvicorn

from ticket_agent.settings import load_settings


def main() -> None:
    """Run uvicorn on the configured host and port with the application factory."""
    settings = load_settings()

    uvicorn.run(
        "ticket_agent.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
