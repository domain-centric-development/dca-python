"""Lending's tables in the kernel's in-memory store."""

from __future__ import annotations

import dataclasses

from dca_building_blocks import DomainEvent

from library.lending.application.shared import (
    LendableCopyRepository,
    LoanLedgerStore,
    LoanRecord,
    ReservationRepository,
)
from library.lending.domain.copy import CopyLent, CopyReturned, CopyShelved, LendableCopy
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import Reservation, ReservationFulfilled, ReservationId, ReservationPlaced
from library.sharedkernel.adapter.outgoing.memory import MemoryDatabase
from library.sharedkernel.application.shared import OrderingKey
from library.sharedkernel.domain.identity import CopyId


@dataclasses.dataclass
class LendingTables:
    """Lending's tables."""

    copies: dict[CopyId, LendableCopy] = dataclasses.field(default_factory=dict)
    reservations: dict[ReservationId, Reservation] = dataclasses.field(default_factory=dict)
    ledger: list[LoanRecord] = dataclasses.field(default_factory=list)


class MemoryLendableCopyRepository(LendableCopyRepository):
    """The copies as the open transaction sees them."""

    def __init__(self, database: MemoryDatabase[LendingTables]) -> None:
        self._database = database

    def _copies(self) -> dict[CopyId, LendableCopy]:
        return self._database.staged().tables.copies

    def find_by_id(self, aggregate_id: CopyId, /) -> LendableCopy | None:
        return self._copies().get(aggregate_id)

    def save(self, aggregate: LendableCopy, /) -> LendableCopy:
        self._copies()[aggregate.id] = aggregate
        return aggregate

    def delete_by_id(self, aggregate_id: CopyId, /) -> None:
        self._copies().pop(aggregate_id, None)


class MemoryReservationRepository(ReservationRepository):
    """The reservations as the open transaction sees them."""

    def __init__(self, database: MemoryDatabase[LendingTables]) -> None:
        self._database = database

    def _reservations(self) -> dict[ReservationId, Reservation]:
        return self._database.staged().tables.reservations

    def find_by_id(self, aggregate_id: ReservationId, /) -> Reservation | None:
        return self._reservations().get(aggregate_id)

    def find_by_id_for_member(self, reservation: ReservationId, member: MemberId, /) -> Reservation | None:
        found = self._reservations().get(reservation)
        return found if found is not None and found.member == member else None

    def save(self, aggregate: Reservation, /) -> Reservation:
        self._reservations()[aggregate.id] = aggregate
        return aggregate

    def delete_by_id(self, aggregate_id: ReservationId, /) -> None:
        self._reservations().pop(aggregate_id, None)


class MemoryLoanLedgerStore(LoanLedgerStore):
    """The ledger as the open transaction sees it."""

    def __init__(self, database: MemoryDatabase[LendingTables]) -> None:
        self._database = database

    def append(self, record: LoanRecord, /) -> None:
        self._database.staged().tables.ledger.append(record)

    def loans_recorded_for(self, member: MemberId, /) -> int:
        return sum(1 for record in self._database.staged().tables.ledger if record.member == member)


def by_aggregate(event: DomainEvent) -> OrderingKey | None:
    """Lending's deliveries are ordered per copy and per reservation."""
    match event:
        case CopyShelved() | CopyLent() | CopyReturned():
            return OrderingKey(f"copy-{event.copy.value}")
        case ReservationPlaced() | ReservationFulfilled():
            return OrderingKey(f"reservation-{event.reservation.value}")
        case _:
            return None
