"""The library's behaviour, end to end through the desks, the stores and the relays."""

from __future__ import annotations

import pytest

from library.catalogue.adapter.incoming.desk import Created, NotFound, Rejected
from library.catalogue.adapter.incoming.desk import DeskResponse as CatalogueResponse
from library.infrastructure import Library
from library.lending.adapter.incoming.desk import DeskResponse as LendingResponse
from library.lending.adapter.incoming.desk import Done, Refused

JANE = 1_001
JOHN = 1_002
SUSPENDED = 1_003


def created(response: CatalogueResponse) -> int:
    assert isinstance(response, Created), f"expected an entry, got {response!r}"
    return response.id


def done(response: LendingResponse) -> int:
    assert isinstance(response, Done), f"expected done, got {response!r}"
    return response.id


@pytest.fixture
def library() -> Library:
    return Library(suspended=[SUSPENDED])


@pytest.fixture
def copy(library: Library) -> int:
    """A title with one copy of it, shelved in lending."""
    title = created(library.catalogue.register_title("Dune"))
    acquired = created(library.catalogue.acquire_copy(title))
    library.relay()
    return acquired


def test_a_title_registered_and_a_copy_acquired_are_held_by_the_catalogue(library: Library) -> None:
    title = created(library.catalogue.register_title("  The Left Hand of Darkness "))
    assert library.title_held(title)

    acquired = library.catalogue.acquire_copy(title)
    assert isinstance(acquired, Created)
    assert acquired.shelf_mark == f"THE-{acquired.id}"
    assert library.holdings_of(title) == 1

    assert library.catalogue.register_title("The Left Hand of Darkness") == Rejected("name-taken")
    assert library.catalogue.register_title(" ") == Rejected("blank-name")
    assert library.catalogue.acquire_copy(424_242) == NotFound()


def test_the_copy_and_its_delivery_to_lending_are_committed_together(library: Library) -> None:
    title = created(library.catalogue.register_title("Dune"))
    assert library.catalogue_deliveries_pending() == 0

    copy = created(library.catalogue.acquire_copy(title))

    assert library.holdings_of(title) == 1
    assert library.catalogue_deliveries_pending() == 1
    assert library.on_shelf(copy) is None, "lending learns of it only after the relay"


def test_the_relay_delivers_after_the_commit_to_the_listener_in_lending(library: Library) -> None:
    title = created(library.catalogue.register_title("Dune"))
    copy = created(library.catalogue.acquire_copy(title))

    assert library.relay() == 1, "the copy acquired; shelving it owes no listener anything"

    assert library.on_shelf(copy) is True
    assert library.catalogue_deliveries_pending() == 0
    assert library.deliveries_received() == 1
    assert library.relay() == 0, "nothing is delivered twice by a relay that recorded its deliveries"


def test_a_repeated_delivery_is_passed_over_by_the_inbox(library: Library, copy: int) -> None:
    done(library.lending.lend(JANE, copy))
    library.relay()

    library.lose_relay_acknowledgements()
    redelivered = library.relay()

    assert redelivered >= 1, "the catalogue's event arrived again"
    assert library.on_shelf(copy) is False, "the copy lent was not shelved anew"
    assert library.loans_of(copy) == 1
    assert library.deliveries_received() == 1


def test_a_member_borrows_a_copy_and_the_reservation_they_collect_is_fulfilled_after_the_commit(
    library: Library, copy: int
) -> None:
    reservation = done(library.lending.reserve(JANE, copy))

    done(library.lending.lend(JANE, copy, reservation))
    assert library.on_shelf(copy) is False
    assert library.reservation_fulfilled(reservation) is False

    library.relay()
    assert library.reservation_fulfilled(reservation) is True

    assert library.lending.lend(JOHN, copy) == Refused("not-on-shelf")


def test_a_reservation_is_fulfilled_when_the_member_collects_the_copy_after_its_return(
    library: Library, copy: int
) -> None:
    done(library.lending.lend(JOHN, copy))
    reservation = done(library.lending.reserve(JANE, copy))
    assert library.lending.lend(JANE, copy, reservation) == Refused("not-on-shelf")

    assert library.lending.give_back(copy) == Done(copy)
    assert library.on_shelf(copy) is True
    assert library.lending.give_back(copy) == Refused("not-on-loan")

    done(library.lending.lend(JANE, copy, reservation))
    library.relay()

    assert library.reservation_fulfilled(reservation) is True
    assert library.loans_of(copy) == 2


def test_another_members_reservation_is_not_reached(library: Library, copy: int) -> None:
    reservation = done(library.lending.reserve(JANE, copy))

    done(library.lending.lend(JOHN, copy, reservation))
    library.relay()

    assert library.reservation_fulfilled(reservation) is False


def test_a_refusal_rolls_back_the_loan_its_record_and_its_delivery(library: Library) -> None:
    title = created(library.catalogue.register_title("Dune"))
    copies = [created(library.catalogue.acquire_copy(title)) for _ in range(3)]
    library.relay()
    done(library.lending.lend(JANE, copies[0], None))
    done(library.lending.lend(JANE, copies[1], None))
    library.relay()
    pending = library.lending_deliveries_pending()

    refused = library.lending.lend(JANE, copies[2])

    assert refused == Refused("loan-limit-reached")
    assert library.on_shelf(copies[2]) is True, "the loan was rolled back"
    assert library.loans_of(copies[2]) == 0
    assert library.loans_recorded() == 2, "the ledger entry was rolled back"
    assert library.lending_deliveries_pending() == pending, "the outbox entry was rolled back"


def test_a_failed_registration_leaves_nothing_behind(library: Library) -> None:
    title = created(library.catalogue.register_title("Dune"))

    assert library.catalogue.register_title("Dune") == Rejected("name-taken")

    assert library.catalogue_deliveries_pending() == 0
    assert library.holdings_of(title) == 0


def test_a_suspended_member_is_refused_by_the_terms_of_lending(library: Library, copy: int) -> None:
    assert library.lending.lend(SUSPENDED, copy) == Refused("member-suspended")
    assert library.on_shelf(copy) is True
    assert library.lending.reserve(JANE, 777) == Refused("unknown-copy")
