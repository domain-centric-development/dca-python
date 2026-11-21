"""The outbox: the deliveries a committed event still owes its transactional listeners, written in the publishing
transaction - by the domain event publisher for a context's own listeners, and by the integration event publisher for
the listeners of other contexts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from dca_building_blocks import (
    DomainEvent,
    DomainEventPublisher,
    EventListener,
    IntegrationEvent,
    IntegrationEventPublisher,
)

from library.sharedkernel.adapter.outgoing.memory import MemoryDatabase
from library.sharedkernel.application.shared import ListenerId, OrderingKey


class Subscriptions:
    """Which listeners react after the commit to which event type: the wiring the publishers read when they register
    deliveries."""

    def __init__(self, listeners: dict[type, tuple[ListenerId, ...]] | None = None) -> None:
        self._listeners = dict(listeners or {})

    def subscribe(self, event_type: type, listener: ListenerId) -> Subscriptions:
        """These subscriptions, and the listener subscribed to the events of `event_type` by its stable name."""
        listeners = dict(self._listeners)
        listeners[event_type] = (*listeners.get(event_type, ()), listener)
        return Subscriptions(listeners)

    def of(self, event_type: type) -> tuple[ListenerId, ...]:
        """The listeners of the events of `event_type`."""
        return self._listeners.get(event_type, ())


class TransactionOutbox:
    """The outbox over the open transaction's table: no port, a part of the publishers' adapters."""

    def __init__(self, database: MemoryDatabase[Any]) -> None:
        self._database = database

    def register(
        self, event: DomainEvent | IntegrationEvent, listener: ListenerId, order: OrderingKey | None = None, /
    ) -> None:
        self._database.staged().outbox.add(event, listener, order)


class IntegrationOutbox(IntegrationEventPublisher):
    """Publishes integration events through the transaction's outbox, one delivery per subscribed listener of another
    context: they leave the context only if the transaction commits."""

    def __init__(self, database: MemoryDatabase[Any], subscriptions: Subscriptions) -> None:
        self._outbox = TransactionOutbox(database)
        self._subscriptions = subscriptions

    def publish(self, event: IntegrationEvent, /) -> None:
        for listener in self._subscriptions.of(type(event)):
            self._outbox.register(event, listener, None)


class TransactionEvents(DomainEventPublisher):
    """The domain event publisher of one store: it calls the listeners that react inside the transaction, then
    registers one outbox entry per listener that reacts after the commit, ordered by the key `ordering` reads from the
    event."""

    def __init__(
        self,
        database: MemoryDatabase[Any],
        subscriptions: Subscriptions,
        ordering: Callable[[DomainEvent], OrderingKey | None],
        reacting: Sequence[EventListener[DomainEvent]] = (),
    ) -> None:
        self._outbox = TransactionOutbox(database)
        self._subscriptions = subscriptions
        self._ordering = ordering
        self._reacting = tuple(reacting)

    def publish(self, event: DomainEvent, /) -> None:
        for listener in self._reacting:
            listener.on(event)
        for subscriber in self._subscriptions.of(type(event)):
            self._outbox.register(event, subscriber, self._ordering(event))
