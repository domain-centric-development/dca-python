from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import UseCase, UseCaseException
from fx.alpha.application.shared import ThingJournal


@dataclasses.dataclass(frozen=True)
class CountThingsQuery:
    at_least: int


@dataclasses.dataclass(frozen=True)
class ThingCountResult:
    count: int


class TooFewThings(UseCaseException):
    def __init__(self, count: int) -> None:
        super().__init__(f"{count} things")
        self.count = count


class CountThingsInputPort(UseCase[CountThingsQuery, ThingCountResult], Protocol):
    pass


class CountThingsUseCase(CountThingsInputPort):
    def __init__(self, journal: ThingJournal) -> None:
        self._journal = journal

    def execute(self, command: CountThingsQuery, /) -> ThingCountResult:
        count = self._journal.count()
        if count < command.at_least:
            raise TooFewThings(count)
        return ThingCountResult(count)
