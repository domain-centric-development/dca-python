"""Adds a copy the library acquired to its title."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, TransactionBoundary, UseCase, UseCaseException

from library.catalogue.application.shared import TitleRepository
from library.catalogue.domain.title import ShelfMark, ShelfMarks
from library.sharedkernel.application.shared import Clock, IdSource
from library.sharedkernel.domain.identity import CopyId, TitleId


@dataclasses.dataclass(frozen=True)
class AcquireCopyCommand:
    title: TitleId


@dataclasses.dataclass(frozen=True)
class AcquireCopyResult:
    copy: CopyId
    shelf_mark: ShelfMark


class TitleNotFound(UseCaseException):
    """Refused: the catalogue holds no such title."""

    def __init__(self, title: TitleId) -> None:
        super().__init__(f"no title {title.value}")
        self.title = title


class AcquireCopyInputPort(UseCase[AcquireCopyCommand, AcquireCopyResult], Protocol):
    pass


class AcquireCopyUseCase(AcquireCopyInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        titles: TitleRepository,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
        marks: ShelfMarks,
    ) -> None:
        self._transactions = transactions
        self._titles = titles
        self._events = events
        self._clock = clock
        self._ids = ids
        self._marks = marks

    def execute(self, command: AcquireCopyCommand, /) -> AcquireCopyResult:
        def work() -> AcquireCopyResult:
            title = self._titles.find_by_id(command.title)
            if title is None:
                raise TitleNotFound(command.title)
            copy = CopyId(self._ids.next_id())
            shelf_mark = title.acquire_copy(self._marks, copy, self._ids.next_event_id(), self._clock.now())
            self._titles.save(title)
            self._events.publish_and_clear_events(title)
            return AcquireCopyResult(copy, shelf_mark)

        return self._transactions.in_transaction(work)
