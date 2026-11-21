"""A copy as lending sees it: on the shelf, or out on loan to a member."""

from __future__ import annotations

from dca_building_blocks import AggregateRoot, DomainEvent, EventId, Specification, Timestamp

from library.lending.domain.failure import NotOnLoan, NotOnShelf
from library.lending.domain.loan import Loan, LoanId, LoanPeriod
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import ReservationId
from library.sharedkernel.domain.identity import CopyId, TitleId


class CopyShelved(DomainEvent):
    """A copy arrived on the shelf, ready to be lent."""

    event_id: EventId
    occurred_on: Timestamp
    copy: CopyId
    title: TitleId


class CopyLent(DomainEvent):
    """A member borrowed a copy, collecting their reservation if they name one."""

    event_id: EventId
    occurred_on: Timestamp
    copy: CopyId
    loan: LoanId
    member: MemberId
    reservation: ReservationId | None
    due: Timestamp


class CopyReturned(DomainEvent):
    """A copy came back."""

    event_id: EventId
    occurred_on: Timestamp
    copy: CopyId
    loan: LoanId


class LendableCopy(AggregateRoot[CopyId]):
    """A copy that may be lent: the aggregate root over its loans."""

    def __init__(self, copy: CopyId, title: TitleId, loans: list[Loan]) -> None:
        self._id = copy
        self._title = title
        self._loans = loans

    @classmethod
    def shelve(cls, copy: CopyId, title: TitleId, event_id: EventId, at: Timestamp) -> LendableCopy:
        """A copy put on the shelf, ready to be lent."""
        shelved = cls(copy, title, [])
        shelved.register_event(CopyShelved(event_id, at, copy, title))
        return shelved

    @property
    def id(self) -> CopyId:
        return self._id

    @property
    def title(self) -> TitleId:
        """The title it is a copy of."""
        return self._title

    def loans(self) -> tuple[Loan, ...]:
        """Its loans, the running one last."""
        return tuple(self._loans)

    def lend(
        self,
        loan: LoanId,
        member: MemberId,
        reservation: ReservationId | None,
        period: LoanPeriod,
        event_id: EventId,
        at: Timestamp,
    ) -> Timestamp:
        """Lends the copy to a member for a period, collecting their reservation if they name one. Answers when it is
        due back."""
        if not OnShelfSpecification().is_satisfied_by(self):
            raise NotOnShelf()
        due = period.due_from(at)
        self._loans.append(Loan(loan, member, due))
        self.register_event(CopyLent(event_id, at, self._id, loan, member, reservation, due))
        return due

    def take_back(self, event_id: EventId, at: Timestamp) -> None:
        """Takes the copy back."""
        running = next((loan for loan in self._loans if loan.is_active()), None)
        if running is None:
            raise NotOnLoan()
        running.end(at)
        self.register_event(CopyReturned(event_id, at, self._id, running.id))


class OnShelfSpecification(Specification[LendableCopy]):
    """A copy on the shelf: none of its loans is running."""

    def is_satisfied_by(self, candidate: LendableCopy) -> bool:
        return not any(loan.is_active() for loan in candidate.loans())
