from __future__ import annotations

import dataclasses
import uuid
from typing import Protocol

from dca_building_blocks import DomainEventPublisher, EventId, Refusal, Timestamp, TransactionBoundary, UseCase
from fx.alpha.application.shared import ThingRepository
from fx.alpha.domain.thing import Label, PartId, ThingId
from fx.sharedkernel.domain.owner import OwnerId


@dataclasses.dataclass(frozen=True)
class AddPartCommand:
    thing_id: ThingId
    owner: OwnerId
    part_id: PartId
    label: Label
    now: Timestamp


@dataclasses.dataclass(frozen=True)
class PartAccepted:
    part_id: PartId


@dataclasses.dataclass(frozen=True)
class ThingMissing(Refusal):
    thing_id: ThingId


type AddPartResult = PartAccepted | ThingMissing


class AddPartInputPort(UseCase[AddPartCommand, AddPartResult], Protocol):
    pass


class AddPartUseCase(AddPartInputPort):
    def __init__(self, things: ThingRepository, events: DomainEventPublisher,
                 transactions: TransactionBoundary) -> None:
        self._things = things
        self._events = events
        self._transactions = transactions

    def execute(self, command: AddPartCommand, /) -> AddPartResult:
        def work() -> AddPartResult:
            thing = self._things.find_for_owner(command.thing_id, command.owner)
            if thing is None:
                return ThingMissing(command.thing_id)
            thing.add_part(command.part_id, command.label, EventId(uuid.uuid4()), command.now)
            self._things.save(thing)
            self._events.publish_and_clear_events(thing)
            return PartAccepted(command.part_id)

        return self._transactions.in_transaction_closed(work)
