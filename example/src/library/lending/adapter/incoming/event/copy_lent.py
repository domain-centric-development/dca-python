"""Fulfils the reservation a member collected: reacts after lending committed the loan, delivered from its outbox, and
drives a use case that runs in a transaction of its own."""

from __future__ import annotations

from typing import assert_never

from dca_building_blocks import TransactionalEventListener

from library.lending.application.fulfil_reservation import (
    Fulfilled,
    FulfilledBefore,
    FulfilReservationCommand,
    FulfilReservationInputPort,
    NoOpenReservation,
)
from library.lending.domain.copy import CopyLent
from library.sharedkernel.application.shared import ListenerId, Received

#: The stable name of the listener that fulfils the reservation a member collected.
FULFIL_COLLECTED_RESERVATION = ListenerId("lending.fulfil-collected-reservation")


class FulfilCollectedReservation(TransactionalEventListener[CopyLent]):
    """Fulfils the reservation a member named when they borrowed the copy."""

    def __init__(self, fulfil: FulfilReservationInputPort) -> None:
        self._fulfil = fulfil

    def on(self, event: CopyLent, /) -> None:
        if event.reservation is None:
            return
        received = Received(event.event_id, FULFIL_COLLECTED_RESERVATION)
        result = self._fulfil.execute(FulfilReservationCommand(received, event.member, event.reservation))
        match result:
            case Fulfilled() | FulfilledBefore():
                return
            case NoOpenReservation():
                # The member named a reservation that is not theirs or closed: the loan stands, nothing to fulfil.
                return
            case _:
                assert_never(result)
