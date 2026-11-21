"""Enters a new title into the catalogue."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, TransactionBoundary, UseCase, UseCaseException

from library.catalogue.application.shared import TitleNameTaken, TitleRepository
from library.catalogue.domain.title import TitleName
from library.catalogue.domain.title_factory import TitleFactory
from library.sharedkernel.application.shared import Clock, IdSource
from library.sharedkernel.domain.identity import TitleId


@dataclasses.dataclass(frozen=True)
class RegisterTitleCommand:
    name: TitleName


@dataclasses.dataclass(frozen=True)
class RegisterTitleResult:
    title: TitleId


class TitleNameInUse(UseCaseException):
    """Refused: the catalogue holds a title of this name already."""

    def __init__(self, name: TitleName) -> None:
        super().__init__(f"a title named {name.value!r} is catalogued already")
        self.name = name


class RegisterTitleInputPort(UseCase[RegisterTitleCommand, RegisterTitleResult], Protocol):
    pass


class RegisterTitleUseCase(RegisterTitleInputPort):
    def __init__(
        self,
        transactions: TransactionBoundary,
        titles: TitleRepository,
        events: DomainEventPublisher,
        clock: Clock,
        ids: IdSource,
        factory: TitleFactory,
    ) -> None:
        self._transactions = transactions
        self._titles = titles
        self._events = events
        self._clock = clock
        self._ids = ids
        self._factory = factory

    def execute(self, command: RegisterTitleCommand, /) -> RegisterTitleResult:
        def work() -> RegisterTitleResult:
            title = self._factory.register(
                TitleId(self._ids.next_id()), command.name, self._ids.next_event_id(), self._clock.now()
            )
            try:
                self._titles.add(title)
            except TitleNameTaken as taken:
                raise TitleNameInUse(taken.name) from taken
            self._events.publish_and_clear_events(title)
            return RegisterTitleResult(title.id)

        return self._transactions.in_transaction(work)
