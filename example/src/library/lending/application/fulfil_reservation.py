"""Closes the reservation a member collected - driven by the copy lent, after lending committed the loan, and passed
over when the same delivery arrives again."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, Refusal, TransactionBoundary, UseCase

from library.lending.application.shared import ReservationRepository
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import ReservationId
from library.sharedkernel.application.shared import Clock, Delivery, IdSource, Inbox, Received


@dataclasses.dataclass(frozen=True)
class FulfilReservationCommand:
    received: Received
    """The delivery that asks for it: the event's id and the listener's name."""
    member: MemberId
    reservation: ReservationId


@dataclasses.dataclass(frozen=True)
class Fulfilled:
    reservation: ReservationId


@dataclasses.dataclass(frozen=True)
class NoOpenReservation(Refusal):
    """Refused: the member holds no such open reservation - another member's, or one fulfilled before. Rolled back
    with the inbox's record, so a repeated delivery is refused again."""

    reservation: ReservationId


@dataclasses.dataclass(frozen=True)
class FulfilledBefore:
    """The delivery arrived before; the reservation was handled then."""

    reservation: ReservationId


type FulfilReservationResult = Fulfilled | NoOpenReservation | FulfilledBefore


class FulfilReservationInputPort(UseCase[FulfilReservationCommand, FulfilReservationResult], Protocol):
    pass


class FulfilReservationUseCase(FulfilReservationInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        inbox: Inbox,
        reservations: ReservationRepository,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
    ) -> None:
        self._transactions = transactions
        self._inbox = inbox
        self._reservations = reservations
        self._events = events
        self._clock = clock
        self._ids = ids

    def execute(self, command: FulfilReservationCommand, /) -> FulfilReservationResult:
        def work() -> FulfilReservationResult:
            if self._inbox.receive(command.received) is Delivery.REPEATED:
                return FulfilledBefore(command.reservation)
            reservation = self._reservations.find_by_id_for_member(command.reservation, command.member)
            if reservation is None or reservation.is_fulfilled():
                return NoOpenReservation(command.reservation)
            reservation.fulfil(self._ids.next_event_id(), self._clock.now())
            self._reservations.save(reservation)
            self._events.publish_and_clear_events(reservation)
            return Fulfilled(command.reservation)

        return self._transactions.in_transaction_closed(work)
