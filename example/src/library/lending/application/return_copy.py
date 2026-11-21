"""A member brings a copy back."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, Refusal, TransactionBoundary, UseCase

from library.lending.application.shared import LendableCopyRepository, UnknownCopy
from library.lending.domain.copy import OnShelfSpecification
from library.sharedkernel.application.shared import Clock, IdSource
from library.sharedkernel.domain.identity import CopyId


@dataclasses.dataclass(frozen=True)
class ReturnCopyCommand:
    copy: CopyId


@dataclasses.dataclass(frozen=True)
class Returned:
    copy: CopyId


@dataclasses.dataclass(frozen=True)
class CopyNotOnLoan(Refusal):
    """Refused: the copy is on the shelf, there is nothing to return."""

    copy: CopyId


type ReturnCopyResult = Returned | UnknownCopy | CopyNotOnLoan


class ReturnCopyInputPort(UseCase[ReturnCopyCommand, ReturnCopyResult], Protocol):
    pass


class ReturnCopyUseCase(ReturnCopyInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        copies: LendableCopyRepository,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
    ) -> None:
        self._transactions = transactions
        self._copies = copies
        self._events = events
        self._clock = clock
        self._ids = ids

    def execute(self, command: ReturnCopyCommand, /) -> ReturnCopyResult:
        def work() -> ReturnCopyResult:
            copy = self._copies.find_by_id(command.copy)
            if copy is None:
                return UnknownCopy(command.copy)
            if OnShelfSpecification().is_satisfied_by(copy):
                return CopyNotOnLoan(command.copy)
            copy.take_back(self._ids.next_event_id(), self._clock.now())
            self._copies.save(copy)
            self._events.publish_and_clear_events(copy)
            return Returned(command.copy)

        return self._transactions.in_transaction_closed(work)
