"""ORM models: the tenants and the tickets that belong to them."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    This function is purely for convenience.
    """
    now = datetime.now(UTC)

    return now


class Base(DeclarativeBase):
    """Declarative base shared by every model so one metadata describes the schema."""


class Tenant(Base):
    """One customer organisation; every ticket belongs to exactly one tenant."""

    __tablename__ = "tenants"

    # Short slug used as the value of the `X-Tenant-ID` header, e.g. `acme`.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Human-readable name shown in the login screen.
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="tenant")


class Ticket(Base):
    """One support ticket. Ids are global integers on purpose.

    A ticket id from another tenant is easy to guess (the brief's "ticket #47"), so the
    only thing that keeps it out of reach is the tenant filter every repository query
    applies. The description is free text written by end users and may contain
    prompt-injection payloads; it is data, never an instruction.
    """

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    description: Mapped[str] = mapped_column(Text, nullable=False)

    # One of `constants.tickets.TICKET_STATUSES`.
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    # One of `constants.tickets.TICKET_PRIORITIES`.
    priority: Mapped[str] = mapped_column(String(32), nullable=False)

    # E-mail address of the person who opened the ticket, as they typed it.
    requester_email: Mapped[str] = mapped_column(String(254), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )

    tenant: Mapped[Tenant] = relationship(back_populates="tickets")
