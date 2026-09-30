"""Tenant-scoped access to the tickets table.

Every public method takes the caller's `tenant_id` as a required argument and puts it in
the WHERE clause. There is no method that reads or writes a ticket without a tenant, so
a cross-tenant access would have to be a new method added here, not a missing argument
somewhere else. A ticket of another tenant is reported exactly like a missing one.
"""

from collections.abc import Mapping

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ticket_agent.constants.tickets import (
    ALLOWED_FIELD_VALUES,
    DEFAULT_TICKET_STATUS,
    MUTABLE_TICKET_FIELDS,
    REQUESTER_EMAIL_MAX_LENGTH,
    SEARCH_RESULT_LIMIT,
    TICKET_PRIORITIES,
    TICKET_TITLE_MAX_LENGTH,
)
from ticket_agent.db.models import Ticket


class TicketNotFound(Exception):
    """No ticket with the given id exists within the caller's tenant.

    Raised identically for a ticket that does not exist and for one that belongs to
    another tenant, so the error cannot be used to probe other tenants' ids.
    """

    def __init__(self, ticket_id: int) -> None:
        """Record the id that was requested."""
        super().__init__(f"ticket {ticket_id} not found")
        self.ticket_id = ticket_id


class InvalidTicketFields(Exception):
    """A change or a new ticket names a field that cannot be set, or gives it a value that
    is empty, too long, or outside its allowed set."""


class TicketRepository:
    """Tenant-scoped queries and changes over the tickets table for one session.

    Write methods commit before returning, so a returned ticket reflects the database.
    """

    def __init__(self, session: Session) -> None:
        """Bind the repository to `session`; the caller owns the session's lifetime."""
        self._session = session

    def validate_update_fields(self, fields: Mapping[str, str]) -> None:
        """Reject an update that touches a fixed column or uses a value outside its set.

        Public so that a caller can check an update before acting on it, for example
        before asking a person to approve one. `update` applies the same check itself.

        Args:
            fields: column name to new value, as supplied by the caller.

        Raises:
            InvalidTicketFields: `fields` is empty, a name is not in
                `MUTABLE_TICKET_FIELDS`, or a constrained column gets a value outside
                `ALLOWED_FIELD_VALUES`.
        """
        is_empty = len(fields) == 0

        if is_empty:
            raise InvalidTicketFields("no fields to update")

        for field_name, new_value in fields.items():
            is_mutable = field_name in MUTABLE_TICKET_FIELDS
            if not is_mutable:
                allowed_names = ", ".join(sorted(MUTABLE_TICKET_FIELDS))
                raise InvalidTicketFields(
                    f"field '{field_name}' cannot be changed; allowed: {allowed_names}"
                )

            allowed_values = ALLOWED_FIELD_VALUES.get(field_name)
            is_constrained = allowed_values is not None
            if is_constrained and new_value not in allowed_values:
                allowed_list = ", ".join(allowed_values)
                raise InvalidTicketFields(
                    f"'{new_value}' is not a valid {field_name}; allowed: {allowed_list}"
                )

    def validate_new_ticket(
        self, title: str, description: str, priority: str, requester_email: str
    ) -> None:
        """Reject a new ticket whose fields are empty, too long or outside their sets.

        Public so that a caller can check a ticket before acting on it, for example
        before asking a person to approve its creation. `create` applies the same check
        itself.

        Args:
            title: the ticket's title; non-empty, at most `TICKET_TITLE_MAX_LENGTH`.
            description: the ticket's text; non-empty.
            priority: one of `TICKET_PRIORITIES`.
            requester_email: the requester's address; non-empty, at most
                `REQUESTER_EMAIL_MAX_LENGTH`, with one `@` inside it.

        Raises:
            InvalidTicketFields: a field breaks one of the rules above.
        """
        normalised_title = title.strip()
        is_title_empty = normalised_title == ""
        if is_title_empty:
            raise InvalidTicketFields("title must not be empty")

        is_title_too_long = len(normalised_title) > TICKET_TITLE_MAX_LENGTH
        if is_title_too_long:
            raise InvalidTicketFields(f"title must be at most {TICKET_TITLE_MAX_LENGTH} characters")

        normalised_description = description.strip()
        is_description_empty = normalised_description == ""
        if is_description_empty:
            raise InvalidTicketFields("description must not be empty")

        is_known_priority = priority in TICKET_PRIORITIES
        if not is_known_priority:
            allowed_priorities = ", ".join(TICKET_PRIORITIES)
            raise InvalidTicketFields(
                f"'{priority}' is not a valid priority; allowed: {allowed_priorities}"
            )

        normalised_email = requester_email.strip()
        is_email_too_long = len(normalised_email) > REQUESTER_EMAIL_MAX_LENGTH
        if is_email_too_long:
            raise InvalidTicketFields(
                f"requester_email must be at most {REQUESTER_EMAIL_MAX_LENGTH} characters"
            )

        # A minimal shape check: something before and after one `@`. Real address
        # validation is out of scope; the seed data uses invented `.example` addresses.
        local_part, separator, domain_part = normalised_email.partition("@")
        is_address_shaped = separator == "@" and local_part != "" and domain_part != ""
        if not is_address_shaped:
            raise InvalidTicketFields("requester_email must look like an e-mail address")

    def create(
        self, tenant_id: str, title: str, description: str, priority: str, requester_email: str
    ) -> Ticket:
        """Insert a new open ticket owned by `tenant_id` and commit.

        The tenant is the caller's, never an argument the model supplies, so a ticket
        can only ever be created within the caller's own tenant. The fields are
        validated first, so an invalid request leaves no trace. The status is always
        `DEFAULT_TICKET_STATUS`.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            title: the ticket's title.
            description: the ticket's text.
            priority: one of `TICKET_PRIORITIES`.
            requester_email: the address of the person the ticket is for.

        Returns:
            The new ticket, with its id.

        Raises:
            InvalidTicketFields: a field is empty, too long or outside its allowed set.
        """
        self.validate_new_ticket(title, description, priority, requester_email)

        ticket = Ticket(
            tenant_id=tenant_id,
            title=title.strip(),
            description=description.strip(),
            status=DEFAULT_TICKET_STATUS,
            priority=priority,
            requester_email=requester_email.strip(),
        )
        self._session.add(ticket)
        self._session.commit()

        return ticket

    def list_for_tenant(self, tenant_id: str) -> list[Ticket]:
        """Return every ticket of `tenant_id`, oldest first.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.

        Returns:
            The tenant's tickets; empty when it has none.
        """
        statement = select(Ticket).where(Ticket.tenant_id == tenant_id).order_by(Ticket.id)
        tickets = list(self._session.scalars(statement))

        return tickets

    def search(self, tenant_id: str, query: str) -> list[Ticket]:
        """Return the tickets of `tenant_id` whose title or description contains `query`.

        Matching is case-insensitive substring matching. An empty or whitespace-only
        query matches every ticket of the tenant. At most `SEARCH_RESULT_LIMIT` rows
        are returned, oldest first.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            query: free text, possibly written by the model.

        Returns:
            The matching tickets; empty when nothing matches.
        """
        normalised_query = query.strip()
        pattern = f"%{normalised_query}%"
        matches_text = or_(Ticket.title.ilike(pattern), Ticket.description.ilike(pattern))

        statement = (
            select(Ticket)
            .where(Ticket.tenant_id == tenant_id)
            .where(matches_text)
            .order_by(Ticket.id)
            .limit(SEARCH_RESULT_LIMIT)
        )
        tickets = list(self._session.scalars(statement))

        return tickets

    def get(self, tenant_id: str, ticket_id: int) -> Ticket:
        """Return the ticket `ticket_id` if it belongs to `tenant_id`.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            ticket_id: the id to look up, possibly supplied by the model.

        Returns:
            The ticket.

        Raises:
            TicketNotFound: the id does not exist or belongs to another tenant.
        """
        statement = (
            select(Ticket).where(Ticket.tenant_id == tenant_id).where(Ticket.id == ticket_id)
        )
        ticket = self._session.scalars(statement).first()
        is_visible_to_tenant = ticket is not None

        if not is_visible_to_tenant:
            raise TicketNotFound(ticket_id)

        return ticket

    def update(self, tenant_id: str, ticket_id: int, fields: Mapping[str, str]) -> Ticket:
        """Change the given fields of the ticket `ticket_id` within `tenant_id`.

        The fields are validated before the ticket is looked up, so an invalid request
        leaves no trace; the tenant check then happens in `get`. `updated_at` is bumped
        by the model's `onupdate`. The change is committed before returning.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            ticket_id: the id to change, possibly supplied by the model.
            fields: column name to new value; must be non-empty.

        Returns:
            The ticket after the change.

        Raises:
            InvalidTicketFields: `fields` is empty, names an immutable or unknown column,
                or gives `status` or `priority` a value outside its allowed set.
            TicketNotFound: the id does not exist or belongs to another tenant.
        """
        self.validate_update_fields(fields)

        ticket = self.get(tenant_id, ticket_id)

        for field_name, new_value in fields.items():
            setattr(ticket, field_name, new_value)

        self._session.commit()

        return ticket

    def delete(self, tenant_id: str, ticket_id: int) -> Ticket:
        """Delete the ticket `ticket_id` within `tenant_id` and return it as it was.

        The change is committed before returning. The returned object is detached and
        keeps the values the ticket had, for reporting.

        Args:
            tenant_id: the caller's tenant, taken from the request, never from a model.
            ticket_id: the id to delete, possibly supplied by the model.

        Returns:
            The deleted ticket's last state.

        Raises:
            TicketNotFound: the id does not exist or belongs to another tenant.
        """
        ticket = self.get(tenant_id, ticket_id)

        self._session.delete(ticket)
        self._session.commit()

        return ticket
