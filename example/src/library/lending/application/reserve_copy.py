"""A member reserves a copy."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, TransactionBoundary, UseCase

from library.lending.application.shared import LendableCopyRepository, ReservationRepository, UnknownCopy
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import Reservation, ReservationId
from library.sharedkernel.application.shared import Clock, IdSource
from library.sharedkernel.domain.identity import CopyId


@dataclasses.dataclass(frozen=True)
class ReserveCopyCommand:
    member: MemberId
    copy: CopyId


@dataclasses.dataclass(frozen=True)
class Reserved:
    reservation: ReservationId


type ReserveCopyResult = Reserved | UnknownCopy


class ReserveCopyInputPort(UseCase[ReserveCopyCommand, ReserveCopyResult], Protocol):
    pass


class ReserveCopyUseCase(ReserveCopyInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        copies: LendableCopyRepository,
        reservations: ReservationRepository,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
    ) -> None:
        self._transactions = transactions
        self._copies = copies
        self._reservations = reservations
        self._events = events
        self._clock = clock
        self._ids = ids

    def execute(self, command: ReserveCopyCommand, /) -> ReserveCopyResult:
        def work() -> ReserveCopyResult:
            if self._copies.find_by_id(command.copy) is None:
                return UnknownCopy(command.copy)
            reservation = Reservation.place(
                ReservationId(self._ids.next_id()),
                command.member,
                command.copy,
                self._ids.next_event_id(),
                self._clock.now(),
            )
            self._reservations.save(reservation)
            self._events.publish_and_clear_events(reservation)
            return Reserved(reservation.id)

        return self._transactions.in_transaction_closed(work)
