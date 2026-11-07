from __future__ import annotations

from collections.abc import Callable

from dca_building_blocks import DomainEvent, DomainEventPublisher, TransactionBoundary
from fx.alpha.application.shared import Tally, ThingJournal, ThingRepository
from fx.alpha.domain.thing import Thing, ThingId
from fx.sharedkernel.domain.owner import OwnerId


class InMemoryThingRepository(ThingRepository):
    def __init__(self) -> None:
        self._things: dict[ThingId, Thing] = {}

    def find_by_id(self, aggregate_id: ThingId, /) -> Thing | None:
        return self._things.get(aggregate_id)

    def find_for_owner(self, thing_id: ThingId, owner: OwnerId, /) -> Thing | None:
        return self._things.get(thing_id)

    def save(self, aggregate: Thing, /) -> Thing:
        self._things[aggregate.id] = aggregate
        return aggregate

    def delete_by_id(self, aggregate_id: ThingId, /) -> None:
        self._things.pop(aggregate_id, None)


class ListJournal(ThingJournal):
    def __init__(self) -> None:
        self._entries: list[ThingId] = []

    def record(self, thing_id: ThingId, /) -> None:
        self._entries.append(thing_id)

    def count(self) -> int:
        return len(self._entries)


class FixedTally(Tally):
    def count(self) -> int:
        return 0


# ListJournal fits Tally by its shape as well; it names the port it implements, so the fit is a coincidence.


class ListPublisher(DomainEventPublisher):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, event: DomainEvent, /) -> None:
        self.published.append(event)


class DirectTransactions(TransactionBoundary):
    def in_transaction[T](self, work: Callable[[], T], /) -> T:
        return work()
