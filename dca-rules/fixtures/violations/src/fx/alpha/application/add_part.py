from __future__ import annotations

import dataclasses
import typing
import uuid

from dca_building_blocks import DomainEventPublisher, Refusal, UseCase
from fx.alpha.application.shared import ThingRepository
from fx.alpha.application.things.remove_part import RemovePartInputPort  # DCA-CYC-005
from fx.alpha.domain.model import Thing, ThingFull


class AddPartCommand:  # DCA-USE-004
    raw: str
    items: list[str]


class LookQuery:  # DCA-USE-005
    pass


class AddPartResult:  # DCA-USE-007
    thing: Thing  # DCA-USE-015


class InputPort(typing.Protocol):  # DCA-USE-001
    pass


@dataclasses.dataclass(frozen=True)
class Found:
    pass


@dataclasses.dataclass(frozen=True)
class NothingFound:
    pass


type LookResult = Found | NothingFound


@dataclasses.dataclass(frozen=True)
class Taken:
    pass


@dataclasses.dataclass(frozen=True)
class Refused(Refusal):
    pass


type TakeResult = Taken | Refused


class AddPartInputPort(UseCase[AddPartCommand, AddPartResult], typing.Protocol):
    pass


class LookInputPort(UseCase[LookQuery, LookResult], typing.Protocol):  # DCA-ERR-008: no case is a refusal
    pass


class TakeInputPort(UseCase[AddPartCommand, TakeResult], typing.Protocol):
    pass


class CountPartsInputPort(UseCase[LookQuery, int], typing.Protocol):  # DCA-USE-022: a bare number answers
    pass


class OnPartAddedInputPort(UseCase[AddPartCommand, AddPartResult], typing.Protocol):  # DCA-NAM-012
    pass


class SetLabelInputPort(UseCase[AddPartCommand, AddPartResult], typing.Protocol):  # DCA-NAM-013
    pass


class AddPartPort(UseCase[AddPartCommand, AddPartResult], typing.Protocol):  # DCA-NAM-003
    pass


class AddPart(AddPartPort):  # DCA-NAM-001, DCA-USE-014: at depth 0, RemovePartUseCase at depth 1
    def execute(self, command: AddPartCommand, /) -> AddPartResult:
        return AddPartResult()


class AddPartUseCase(AddPartInputPort):
    def __init__(self, things: ThingRepository, events: DomainEventPublisher, other: RemovePartInputPort) -> None:
        self._things = things
        self._events = events
        self._other = other  # DCA-USE-016

    def execute(self, command: AddPartCommand, /) -> AddPartResult:
        uuid.UUID(command.raw)  # DCA-USE-020
        thing = self._things.find_by_id(command.raw)
        self._things.save(thing)  # DCA-USE-009, DCA-USE-012
        if thing is None:
            raise ThingFull()  # DCA-ERR-009
        return AddPartResult()

    def helper(self) -> None:  # DCA-USE-017
        try:
            pass
        except BaseException:  # DCA-PY-007
            pass


class LookUseCase(LookInputPort):
    def __init__(self, things: ThingRepository) -> None:
        self._things = things

    def execute(self, command: LookQuery, /) -> LookResult:
        self._last = command  # DCA-USE-021: the use case keeps the last query
        self._things.save(None)  # DCA-USE-019
        return NothingFound()
