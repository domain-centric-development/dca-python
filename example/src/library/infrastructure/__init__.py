"""The composition root: builds both contexts over their stores, the desks that drive them and the relays that carry
events after the commit - the catalogue's to lending, lending's to itself."""

from __future__ import annotations

from collections.abc import Iterable

from library.catalogue.adapter.incoming.desk import CatalogueDesk
from library.catalogue.adapter.outgoing.memory import CatalogueTables, MemoryTitleRepository
from library.catalogue.adapter.outgoing.publication import PublishCopyAcquired, by_title
from library.catalogue.adapter.outgoing.shelving import InitialsShelfMarks
from library.catalogue.application.acquire_copy import AcquireCopyUseCase
from library.catalogue.application.register_title import RegisterTitleUseCase
from library.catalogue.domain.title_factory import TitleFactory
from library.catalogue.events import CopyAcquired
from library.lending.adapter.incoming.desk import LendingDesk
from library.lending.adapter.incoming.event.copy_acquired import SHELVE_ACQUIRED_COPY, ShelveAcquiredCopy
from library.lending.adapter.incoming.event.copy_lent import FULFIL_COLLECTED_RESERVATION, FulfilCollectedReservation
from library.lending.adapter.outgoing.membership import SuspensionList
from library.lending.adapter.outgoing.memory import (
    LendingTables,
    MemoryLendableCopyRepository,
    MemoryLoanLedgerStore,
    MemoryReservationRepository,
    by_aggregate,
)
from library.lending.application.fulfil_reservation import FulfilReservationUseCase
from library.lending.application.lend_copy import LendCopyUseCase
from library.lending.application.reserve_copy import ReserveCopyUseCase
from library.lending.application.return_copy import ReturnCopyUseCase
from library.lending.application.shelve_copy import ShelveCopyUseCase
from library.lending.domain.copy import CopyLent, OnShelfSpecification
from library.lending.domain.loan import LoanPeriod
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import ReservationId
from library.lending.domain.terms import LoanTerms
from library.sharedkernel.adapter.outgoing.inbox import TransactionInbox
from library.sharedkernel.adapter.outgoing.memory import MemoryDatabase
from library.sharedkernel.adapter.outgoing.outbox import IntegrationOutbox, Subscriptions, TransactionEvents
from library.sharedkernel.adapter.outgoing.relay import Relay
from library.sharedkernel.adapter.outgoing.system import SequentialIds, SystemClock
from library.sharedkernel.domain.identity import CopyId, TitleId

#: How long a member may keep a copy.
REGULAR_LOAN_PERIOD = LoanPeriod(21)


class Library:
    """The library, wired: the two desks, the relays, and a few reads of the committed stores for whoever runs it."""

    def __init__(self, suspended: Iterable[int] = ()) -> None:
        clock = SystemClock()
        ids = SequentialIds()

        self._catalogue_store = MemoryDatabase(CatalogueTables())
        self._lending_store = MemoryDatabase(LendingTables())
        catalogue_subscriptions = Subscriptions().subscribe(CopyAcquired, SHELVE_ACQUIRED_COPY)
        lending_subscriptions = Subscriptions().subscribe(CopyLent, FULFIL_COLLECTED_RESERVATION)

        titles = MemoryTitleRepository(self._catalogue_store)
        integration = IntegrationOutbox(self._catalogue_store, catalogue_subscriptions)
        title_events = TransactionEvents(
            self._catalogue_store, catalogue_subscriptions, by_title, reacting=(PublishCopyAcquired(integration),)
        )
        self.catalogue = CatalogueDesk(
            RegisterTitleUseCase(self._catalogue_store, titles, title_events, clock, ids, TitleFactory()),
            AcquireCopyUseCase(self._catalogue_store, titles, title_events, clock, ids, InitialsShelfMarks()),
        )

        copies = MemoryLendableCopyRepository(self._lending_store)
        reservations = MemoryReservationRepository(self._lending_store)
        inbox = TransactionInbox(self._lending_store)
        lending_events = TransactionEvents(self._lending_store, lending_subscriptions, by_aggregate)
        terms = LoanTerms(REGULAR_LOAN_PERIOD, SuspensionList(MemberId(member) for member in suspended))
        ledger = MemoryLoanLedgerStore(self._lending_store)
        self.lending = LendingDesk(
            LendCopyUseCase(self._lending_store, copies, ledger, lending_events, clock, ids, terms),
            ReturnCopyUseCase(self._lending_store, copies, lending_events, clock, ids),
            ReserveCopyUseCase(self._lending_store, copies, reservations, lending_events, clock, ids),
        )

        shelve = ShelveCopyUseCase(self._lending_store, inbox, copies, lending_events, clock, ids)
        fulfil = FulfilReservationUseCase(self._lending_store, inbox, reservations, lending_events, clock, ids)
        self._catalogue_relay = Relay(self._catalogue_store).route(
            CopyAcquired, SHELVE_ACQUIRED_COPY, ShelveAcquiredCopy(shelve)
        )
        self._lending_relay = Relay(self._lending_store).route(
            CopyLent, FULFIL_COLLECTED_RESERVATION, FulfilCollectedReservation(fulfil)
        )

    def relay(self) -> int:
        """Runs both relays once: what the catalogue committed reaches lending, then what lending committed reaches
        its own listeners. Answers how many deliveries were made."""
        return self._catalogue_relay.deliver() + self._lending_relay.deliver()

    def lose_relay_acknowledgements(self) -> None:
        """Forgets the deliveries both relays made, as a relay that stopped before recording them."""
        self._catalogue_store.forget_deliveries()
        self._lending_store.forget_deliveries()

    def catalogue_deliveries_pending(self) -> int:
        """The deliveries the catalogue still owes."""
        return self._catalogue_store.read(lambda staged: staged.outbox.pending())

    def lending_deliveries_pending(self) -> int:
        """The deliveries lending still owes its own listeners."""
        return self._lending_store.read(lambda staged: staged.outbox.pending())

    def title_held(self, title: int) -> bool:
        """Whether the catalogue holds the title."""
        return self._catalogue_store.read(lambda staged: TitleId(title) in staged.tables.titles)

    def holdings_of(self, title: int) -> int | None:
        """How many copies the catalogue holds of the title."""
        found = self._catalogue_store.read(lambda staged: staged.tables.titles.get(TitleId(title)))
        return None if found is None else len(found.holdings())

    def on_shelf(self, copy: int) -> bool | None:
        """Whether lending knows the copy, and whether it is on the shelf."""
        found = self._lending_store.read(lambda staged: staged.tables.copies.get(CopyId(copy)))
        return None if found is None else OnShelfSpecification().is_satisfied_by(found)

    def loans_of(self, copy: int) -> int:
        """The loans lending made of the copy."""
        found = self._lending_store.read(lambda staged: staged.tables.copies.get(CopyId(copy)))
        return 0 if found is None else len(found.loans())

    def reservation_fulfilled(self, reservation: int) -> bool | None:
        """Whether the reservation was fulfilled."""
        found = self._lending_store.read(lambda staged: staged.tables.reservations.get(ReservationId(reservation)))
        return None if found is None else found.is_fulfilled()

    def loans_recorded(self) -> int:
        """How many loans the ledger records."""
        return self._lending_store.read(lambda staged: len(staged.tables.ledger))

    def deliveries_received(self) -> int:
        """How many deliveries lending's inbox received."""
        return self._lending_store.read(lambda staged: len(staged.inbox.received))
