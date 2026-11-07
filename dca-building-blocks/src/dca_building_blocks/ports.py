"""Ports: what the application offers (input ports) and what it needs (output ports).

Every port is a `typing.Protocol`, so the type checker can hold an adapter to its shape. A role stays nominal
all the same: a use case names its input port among its bases, an outgoing adapter the output port it implements,
so the rule suite sees who implements what.
"""

from __future__ import annotations

import typing

from dca_building_blocks.tactical import AggregateRoot, DomainEvent, Id, IntegrationEvent


class InputPort(typing.Protocol):
    """Marks a protocol as an input port: an entry to the application, called by an incoming adapter, which
    depends on the port and never on the use case that implements it."""


class UseCase[I, O](InputPort, typing.Protocol):
    """An input port with one operation that takes a command or a query and answers with a result, never with an
    entity. The port is `<Action><Concept>InputPort(UseCase[<Command>, <Result>], Protocol)` and declares nothing
    of its own; the class implementing it is `<Action><Concept>UseCase(<its port>)`."""

    def execute(self, command: I, /) -> O:
        """Run the use case."""
        ...


class AsyncUseCase[I, O](InputPort, typing.Protocol):
    """`UseCase` for an application whose ports are coroutines. The domain stays synchronous."""

    async def execute(self, command: I, /) -> O:
        """Run the use case."""
        ...


class OutputPort(typing.Protocol):
    """Marks a protocol as an output port: what the application needs from outside, declared in the application,
    implemented by an outgoing adapter."""


class Repository[A: AggregateRoot[typing.Any], K: Id](OutputPort, typing.Protocol):
    """Loads and saves the aggregates of one root type by their identity, one repository per root. The bound makes
    a repository for anything but an aggregate root a type error. A port adds the questions its use cases ask."""

    def find_by_id(self, aggregate_id: K, /) -> A | None:
        """The aggregate with this identity, or None."""
        ...

    def save(self, aggregate: A, /) -> A:
        """Add or update the aggregate; its events are published by the use case afterwards."""
        ...

    def delete_by_id(self, aggregate_id: K, /) -> None:
        """Remove the aggregate with this identity."""
        ...


class Store(OutputPort, typing.Protocol):
    """Records or looks up operational data without an aggregate life cycle: a journal appended to, a log read. It
    reads and appends; it never saves or deletes an element."""


class DomainEventPublisher(OutputPort, typing.Protocol):
    """Publishes an aggregate's domain events after it was saved."""

    def publish(self, event: DomainEvent, /) -> None:
        """Publish one event."""
        ...

    def publish_and_clear_events(self, aggregate: AggregateRoot[typing.Any], /) -> None:
        """Publish every event the aggregate recorded, then clear them."""
        for event in aggregate.domain_events():
            self.publish(event)
        aggregate.clear_domain_events()


class IntegrationEventPublisher(OutputPort, typing.Protocol):
    """Publishes integration events for other bounded contexts."""

    def publish(self, event: IntegrationEvent, /) -> None:
        """Publish one event."""
        ...
