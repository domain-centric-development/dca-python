"""Puts a copy the catalogue acquired on lending's shelf - driven by the catalogue's event, after the catalogue
committed, and passed over when the same delivery arrives again."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, TransactionBoundary, UseCase

from library.lending.application.shared import LendableCopyRepository
from library.lending.domain.copy import LendableCopy
from library.sharedkernel.application.shared import Clock, Delivery, IdSource, Inbox, Received
from library.sharedkernel.domain.identity import CopyId, TitleId


@dataclasses.dataclass(frozen=True)
class ShelveCopyCommand:
    received: Received
    """The delivery that asks for it: the event's id and the listener's name."""
    copy: CopyId
    title: TitleId


@dataclasses.dataclass(frozen=True)
class ShelveCopyResult:
    """The copy stands on the shelf - shelved now on the first delivery, before on a repeated one."""

    copy: CopyId
    delivery: Delivery


class ShelveCopyInputPort(UseCase[ShelveCopyCommand, ShelveCopyResult], Protocol):
    pass


class ShelveCopyUseCase(ShelveCopyInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        inbox: Inbox,
        copies: LendableCopyRepository,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
    ) -> None:
        self._transactions = transactions
        self._inbox = inbox
        self._copies = copies
        self._events = events
        self._clock = clock
        self._ids = ids

    def execute(self, command: ShelveCopyCommand, /) -> ShelveCopyResult:
        def work() -> ShelveCopyResult:
            if self._inbox.receive(command.received) is Delivery.REPEATED:
                return ShelveCopyResult(command.copy, Delivery.REPEATED)
            copy = LendableCopy.shelve(command.copy, command.title, self._ids.next_event_id(), self._clock.now())
            self._copies.save(copy)
            self._events.publish_and_clear_events(copy)
            return ShelveCopyResult(command.copy, Delivery.FIRST)

        return self._transactions.in_transaction(work)
