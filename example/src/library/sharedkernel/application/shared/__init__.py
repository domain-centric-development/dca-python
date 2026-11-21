"""The output ports every context's use cases share, and the vocabulary of event delivery: which listener a
delivery goes to, in which order, and whether it arrived before."""

from __future__ import annotations

import dataclasses
import enum
from typing import Protocol

from dca_building_blocks import EventId, OutputPort, Store, Timestamp


class Clock(OutputPort, Protocol):
    """What time it is: the domain never reads a clock, the use case asks this port."""

    def now(self) -> Timestamp: ...


class IdSource(OutputPort, Protocol):
    """Fresh identities, for aggregates and for events."""

    def next_id(self) -> int:
        """The number of a new identity; the use case wraps it in the id type it needs."""
        ...

    def next_event_id(self) -> EventId:
        """A new event identity."""
        ...


@dataclasses.dataclass(frozen=True, slots=True)
class ListenerId:
    """The stable name of a listener that reacts after the commit: what the outbox records for a delivery still to
    make and the inbox for one made. It names what the listener does, not a class path, so a renamed or moved class
    keeps its pending deliveries."""

    name: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a listener id has a name")


@dataclasses.dataclass(frozen=True, slots=True)
class OrderingKey:
    """What orders deliveries: the entries with the same key reach their listener one after the other, in the order
    they were registered - the identity of the aggregate whose events they are."""

    key: str


@dataclasses.dataclass(frozen=True, slots=True)
class Received:
    """Which delivery a listener-driven use case runs for: the event's id and the listener's name. The command carries
    it, and the use case hands it to the `Inbox` before it does anything else."""

    event: EventId
    listener: ListenerId


class Delivery(enum.Enum):
    """Whether a delivery reached its listener before."""

    FIRST = "first"
    """New: the listener reacts."""
    REPEATED = "repeated"
    """Received before: the listener has reacted already and does nothing."""


class Inbox(Store, Protocol):
    """The record of the deliveries each listener received, kept in the listener's transaction so a rolled-back
    reaction is received again. Delivery is at least once; this is how a repeat is passed over. It appends and reads,
    so it is a store."""

    def receive(self, received: Received, /) -> Delivery:
        """Record the delivery and answer whether it is new."""
        ...
