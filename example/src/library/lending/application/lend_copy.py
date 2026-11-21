"""A member borrows a copy - for the period the terms of lending give them, within their limit of loans."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, Refusal, Timestamp, TransactionBoundary, UseCase

from library.lending.application.shared import LendableCopyRepository, LoanLedgerStore, LoanRecord, UnknownCopy
from library.lending.domain.copy import OnShelfSpecification
from library.lending.domain.loan import LoanId
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import ReservationId
from library.lending.domain.terms import LoanTerms
from library.sharedkernel.application.shared import Clock, IdSource
from library.sharedkernel.domain.identity import CopyId

#: How many loans the ledger may record for one member.
LOAN_LIMIT = 2


@dataclasses.dataclass(frozen=True)
class LendCopyCommand:
    copy: CopyId
    member: MemberId
    reservation: ReservationId | None = None
    """The reservation the member collects, if any."""


@dataclasses.dataclass(frozen=True)
class Lent:
    loan: LoanId
    due: Timestamp


@dataclasses.dataclass(frozen=True)
class CopyNotOnShelf(Refusal):
    """Refused: the copy is out on loan."""

    copy: CopyId


@dataclasses.dataclass(frozen=True)
class MemberSuspended(Refusal):
    """Refused: the member is suspended."""

    member: MemberId


@dataclasses.dataclass(frozen=True)
class LoanLimitReached(Refusal):
    """Refused: the member has borrowed as many copies as they may."""

    member: MemberId
    limit: int


type LendCopyResult = Lent | UnknownCopy | CopyNotOnShelf | MemberSuspended | LoanLimitReached


class LendCopyInputPort(UseCase[LendCopyCommand, LendCopyResult], Protocol):
    pass


class LendCopyUseCase(LendCopyInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        copies: LendableCopyRepository,
        ledger: LoanLedgerStore,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
        terms: LoanTerms,
    ) -> None:
        self._transactions = transactions
        self._copies = copies
        self._ledger = ledger
        self._events = events
        self._clock = clock
        self._ids = ids
        self._terms = terms

    def execute(self, command: LendCopyCommand, /) -> LendCopyResult:
        def work() -> LendCopyResult:
            copy = self._copies.find_by_id(command.copy)
            if copy is None:
                return UnknownCopy(command.copy)
            period = self._terms.period_for(copy, command.member)
            if period is None:
                return MemberSuspended(command.member)
            if not OnShelfSpecification().is_satisfied_by(copy):
                return CopyNotOnShelf(command.copy)
            loan = LoanId(self._ids.next_id())
            now = self._clock.now()
            due = copy.lend(loan, command.member, command.reservation, period, self._ids.next_event_id(), now)
            self._copies.save(copy)
            self._events.publish_and_clear_events(copy)
            self._ledger.append(LoanRecord(loan, command.copy, command.member, now))
            # The ledger counts the loan just made: over the limit, the transaction is rolled back - the copy, its
            # event and the record alike.
            if self._ledger.loans_recorded_for(command.member) > LOAN_LIMIT:
                return LoanLimitReached(command.member, LOAN_LIMIT)
            return Lent(loan, due)

        return self._transactions.in_transaction_closed(work)
