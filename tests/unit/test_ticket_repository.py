"""`TicketRepository`: every query takes the tenant, and a foreign ticket is a missing one."""

import pytest
from sqlalchemy.orm import Session

from tests.constants.seed import ACME_TICKET_IDS, GLOBEX_TICKET_IDS, UNKNOWN_TICKET_ID
from ticket_agent.constants.seed import (
    ACME_TENANT_ID,
    GLOBEX_TENANT_ID,
    TARGET_FOREIGN_TICKET_ID,
)
from ticket_agent.constants.tickets import (
    DEFAULT_TICKET_STATUS,
    REQUESTER_EMAIL_MAX_LENGTH,
    SEARCH_RESULT_LIMIT,
    TICKET_TITLE_MAX_LENGTH,
)
from ticket_agent.tickets.repository import (
    InvalidTicketFields,
    TicketNotFound,
    TicketRepository,
)


@pytest.fixture
def repository(session: Session) -> TicketRepository:
    """A repository over the seeded database."""
    ticket_repository = TicketRepository(session)

    return ticket_repository


def ids_of(tickets: list) -> list[int]:
    """Return the ids of ticket rows in order.

    Args:
        tickets: ticket rows.

    Returns:
        Their ids.
    """
    ticket_ids = []
    for ticket in tickets:
        ticket_ids.append(ticket.id)

    return ticket_ids


def test_list_for_tenant_returns_only_that_tenants_tickets(repository: TicketRepository) -> None:
    """Each tenant's listing holds its own seed rows and none of the other's."""
    acme_tickets = repository.list_for_tenant(ACME_TENANT_ID)
    globex_tickets = repository.list_for_tenant(GLOBEX_TENANT_ID)

    assert ids_of(acme_tickets) == ACME_TICKET_IDS
    assert ids_of(globex_tickets) == GLOBEX_TICKET_IDS


def test_search_matches_the_title_case_insensitively(repository: TicketRepository) -> None:
    """A query is matched as a substring of the title, ignoring case."""
    matches = repository.search(ACME_TENANT_ID, "INVOICE")

    assert ids_of(matches) == [2]


def test_search_matches_the_description(repository: TicketRepository) -> None:
    """A query is matched as a substring of the description too."""
    matches = repository.search(ACME_TENANT_ID, "mobile app")

    assert ids_of(matches) == [1]


def test_search_with_blank_query_returns_every_ticket_of_the_tenant(
    repository: TicketRepository,
) -> None:
    """Whitespace or an empty string lists the tenant's tickets, oldest first."""
    all_tickets = repository.search(ACME_TENANT_ID, "   ")

    assert ids_of(all_tickets) == ACME_TICKET_IDS


def test_search_never_crosses_tenants_even_with_a_matching_foreign_text(
    repository: TicketRepository,
) -> None:
    """A query that only a Globex ticket matches finds nothing for Acme."""
    matches = repository.search(ACME_TENANT_ID, "merger data room")

    assert matches == []


def test_search_is_capped_at_the_result_limit(
    repository: TicketRepository, session: Session
) -> None:
    """More matching rows than the limit are cut at the limit."""
    for index in range(SEARCH_RESULT_LIMIT + 5):
        repository.create(
            ACME_TENANT_ID,
            f"Bulk ticket {index}",
            "Created to exceed the search limit.",
            "low",
            "bulk@acme.example",
        )

    matches = repository.search(ACME_TENANT_ID, "Bulk ticket")

    assert len(matches) == SEARCH_RESULT_LIMIT


def test_get_returns_the_tenants_ticket(repository: TicketRepository) -> None:
    """A ticket of the caller's tenant is returned with its fields."""
    ticket = repository.get(ACME_TENANT_ID, 3)

    assert ticket.title == "Export to CSV is missing the last column"
    assert ticket.tenant_id == ACME_TENANT_ID


def test_get_reports_a_foreign_ticket_exactly_like_a_missing_one(
    repository: TicketRepository,
) -> None:
    """Globex's ticket 47 and an unknown id raise the same error text for Acme."""
    with pytest.raises(TicketNotFound) as foreign_failure:
        repository.get(ACME_TENANT_ID, TARGET_FOREIGN_TICKET_ID)
    with pytest.raises(TicketNotFound) as missing_failure:
        repository.get(ACME_TENANT_ID, UNKNOWN_TICKET_ID)

    foreign_text = str(foreign_failure.value).replace(str(TARGET_FOREIGN_TICKET_ID), "N")
    missing_text = str(missing_failure.value).replace(str(UNKNOWN_TICKET_ID), "N")
    assert foreign_text == missing_text


def test_update_changes_the_named_fields_and_commits(
    repository: TicketRepository, session: Session
) -> None:
    """An update writes the new values and a fresh read sees them."""
    repository.update(ACME_TENANT_ID, 1, {"status": "closed", "priority": "low"})

    session.expire_all()
    ticket = repository.get(ACME_TENANT_ID, 1)
    assert ticket.status == "closed"
    assert ticket.priority == "low"


@pytest.mark.parametrize(
    ("fields", "expected_fragment"),
    [
        ({}, "no fields"),
        ({"tenant_id": GLOBEX_TENANT_ID}, "cannot be changed"),
        ({"id": "5"}, "cannot be changed"),
        ({"status": "done"}, "not a valid status"),
        ({"priority": "urgent"}, "not a valid priority"),
    ],
)
def test_update_rejects_immutable_fields_and_unknown_values(
    repository: TicketRepository, fields: dict[str, str], expected_fragment: str
) -> None:
    """Fixed columns and values outside the allowed sets are refused before any lookup."""
    with pytest.raises(InvalidTicketFields) as failure:
        repository.update(ACME_TENANT_ID, 1, fields)

    assert expected_fragment in str(failure.value)


def test_update_of_a_foreign_ticket_is_not_found_and_changes_nothing(
    repository: TicketRepository,
) -> None:
    """Acme cannot update Globex's ticket; the row keeps its values."""
    with pytest.raises(TicketNotFound):
        repository.update(ACME_TENANT_ID, TARGET_FOREIGN_TICKET_ID, {"status": "closed"})

    ticket = repository.get(GLOBEX_TENANT_ID, TARGET_FOREIGN_TICKET_ID)
    assert ticket.status == "open"


def test_delete_removes_the_ticket_and_returns_its_last_state(
    repository: TicketRepository,
) -> None:
    """The deleted row is gone from the listing and its values are returned."""
    deleted_ticket = repository.delete(ACME_TENANT_ID, 2)

    assert deleted_ticket.title == "Invoice PDF shows wrong billing address"
    assert 2 not in ids_of(repository.list_for_tenant(ACME_TENANT_ID))


def test_delete_of_a_foreign_ticket_is_not_found_and_keeps_the_row(
    repository: TicketRepository,
) -> None:
    """Acme cannot delete Globex's ticket; Globex still lists it."""
    with pytest.raises(TicketNotFound):
        repository.delete(ACME_TENANT_ID, TARGET_FOREIGN_TICKET_ID)

    assert TARGET_FOREIGN_TICKET_ID in ids_of(repository.list_for_tenant(GLOBEX_TENANT_ID))


def test_create_inserts_an_open_ticket_in_the_given_tenant(
    repository: TicketRepository,
) -> None:
    """A created ticket is open, trimmed, and listed for its tenant only."""
    ticket = repository.create(
        ACME_TENANT_ID, "  New printer  ", " Jams daily. ", "high", " who@acme.example "
    )

    assert ticket.status == DEFAULT_TICKET_STATUS
    assert ticket.title == "New printer"
    assert ticket.description == "Jams daily."
    assert ticket.requester_email == "who@acme.example"
    assert ticket.id in ids_of(repository.list_for_tenant(ACME_TENANT_ID))
    assert ticket.id not in ids_of(repository.list_for_tenant(GLOBEX_TENANT_ID))


@pytest.mark.parametrize(
    ("title", "description", "priority", "requester_email", "expected_fragment"),
    [
        (" ", "text", "low", "a@b.example", "title must not be empty"),
        ("t" * (TICKET_TITLE_MAX_LENGTH + 1), "text", "low", "a@b.example", "at most"),
        ("title", "  ", "low", "a@b.example", "description must not be empty"),
        ("title", "text", "urgent", "a@b.example", "not a valid priority"),
        ("title", "text", "low", "no-at-sign", "look like an e-mail"),
        ("title", "text", "low", "@domain.example", "look like an e-mail"),
        ("title", "text", "low", "a" * REQUESTER_EMAIL_MAX_LENGTH + "@x", "at most"),
    ],
)
def test_create_rejects_bad_fields_without_inserting(
    repository: TicketRepository,
    title: str,
    description: str,
    priority: str,
    requester_email: str,
    expected_fragment: str,
) -> None:
    """Each rule of a new ticket is enforced and nothing is written when one fails."""
    count_before = len(repository.list_for_tenant(ACME_TENANT_ID))

    with pytest.raises(InvalidTicketFields) as failure:
        repository.create(ACME_TENANT_ID, title, description, priority, requester_email)

    assert expected_fragment in str(failure.value)
    assert len(repository.list_for_tenant(ACME_TENANT_ID)) == count_before
