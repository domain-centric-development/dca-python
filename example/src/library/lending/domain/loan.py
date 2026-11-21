"""A loan of a copy: active until the copy comes back, then returned."""

from __future__ import annotations

import datetime

from dca_building_blocks import Entity, Id, Timestamp, Value

from library.lending.domain.member import MemberId


class LoanId(Id):
    """A loan of a copy."""

    value: int


class LoanPeriod(Value):
    """How long a loan runs: `value` whole days."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError("a loan runs at least a day")

    def due_from(self, start: Timestamp) -> Timestamp:
        """The moment a loan that starts at `start` is due back."""
        return Timestamp(start.value + datetime.timedelta(days=self.value))

    def halved(self) -> LoanPeriod:
        """Half the period, a day at least."""
        return LoanPeriod(max(self.value // 2, 1))


class Loan(Entity[LoanId]):
    """A loan, running until the copy is returned."""

    def __init__(self, loan: LoanId, member: MemberId, due: Timestamp, returned_on: Timestamp | None = None) -> None:
        self._id = loan
        self._member = member
        self._due = due
        self._returned_on = returned_on

    @property
    def id(self) -> LoanId:
        return self._id

    @property
    def member(self) -> MemberId:
        """Who borrowed the copy."""
        return self._member

    @property
    def due(self) -> Timestamp:
        """When the copy is due back."""
        return self._due

    @property
    def returned_on(self) -> Timestamp | None:
        """When the copy came back, while it is out nothing."""
        return self._returned_on

    def is_active(self) -> bool:
        """Whether the copy is still out."""
        return self._returned_on is None

    def end(self, at: Timestamp) -> None:
        """The copy came back; a returned loan stays as it was."""
        if self._returned_on is None:
            self._returned_on = at
