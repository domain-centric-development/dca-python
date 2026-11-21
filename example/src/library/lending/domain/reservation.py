"""A member's reservation of a copy: it belongs to the member and is reached only through them."""

from __future__ import annotations

from dca_building_blocks import AggregateRoot, DomainEvent, EventId, Id, Owned, Timestamp

from library.lending.domain.failure import ReservationClosed
from library.lending.domain.member import MemberId
from library.sharedkernel.domain.identity import CopyId


class ReservationId(Id):
    """A reservation."""

    value: int


class ReservationPlaced(DomainEvent):
    """A member reserved a copy."""

    event_id: EventId
    occurred_on: Timestamp
    reservation: ReservationId
    member: MemberId
    copy: CopyId


class ReservationFulfilled(DomainEvent):
    """The member collected the reserved copy."""

    event_id: EventId
    occurred_on: Timestamp
    reservation: ReservationId


class Reservation(AggregateRoot[ReservationId], Owned[MemberId]):
    """A member's reservation of a copy."""

    def __init__(self, reservation: ReservationId, member: MemberId, copy: CopyId, fulfilled: bool) -> None:
        self._id = reservation
        self._member = member
        self._copy = copy
        self._fulfilled = fulfilled

    @classmethod
    def place(
        cls, reservation: ReservationId, member: MemberId, copy: CopyId, event_id: EventId, at: Timestamp
    ) -> Reservation:
        """A member reserves a copy."""
        placed = cls(reservation, member, copy, fulfilled=False)
        placed.register_event(ReservationPlaced(event_id, at, reservation, member, copy))
        return placed

    @property
    def id(self) -> ReservationId:
        return self._id

    @property
    def member(self) -> MemberId:
        """The member it belongs to."""
        return self._member

    @property
    def copy(self) -> CopyId:
        """The copy reserved."""
        return self._copy

    def is_fulfilled(self) -> bool:
        """Whether the member collected the copy."""
        return self._fulfilled

    def fulfil(self, event_id: EventId, at: Timestamp) -> None:
        """The member collected the copy; a reservation is fulfilled once."""
        if self._fulfilled:
            raise ReservationClosed()
        self._fulfilled = True
        self.register_event(ReservationFulfilled(event_id, at, self._id))
