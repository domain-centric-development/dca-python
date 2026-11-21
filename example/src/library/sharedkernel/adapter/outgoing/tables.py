"""The kernel's tables beside every context's own: the outbox - the deliveries a committed event still owes its
listeners - and the inbox - the deliveries each listener has received."""

from __future__ import annotations

import dataclasses

from library.sharedkernel.application.shared import ListenerId, OrderingKey, Received


@dataclasses.dataclass
class OutboxEntry:
    """One delivery an event owes one listener."""

    sequence: int
    listener: ListenerId
    order: OrderingKey | None
    payload: object
    delivered: bool = False


@dataclasses.dataclass
class OutboxTable:
    """The outbox, as a transaction sees it."""

    entries: list[OutboxEntry] = dataclasses.field(default_factory=list)
    last: int = 0

    def add(self, payload: object, listener: ListenerId, order: OrderingKey | None) -> None:
        self.last += 1
        self.entries.append(OutboxEntry(self.last, listener, order, payload))

    def pending(self) -> int:
        """How many deliveries are still to make."""
        return sum(1 for entry in self.entries if not entry.delivered)

    def undelivered(self) -> list[OutboxEntry]:
        """The deliveries still to make, in the order they were registered."""
        return [entry for entry in self.entries if not entry.delivered]

    def mark_delivered(self, sequence: int) -> None:
        for entry in self.entries:
            if entry.sequence == sequence:
                entry.delivered = True

    def forget_deliveries(self) -> None:
        """Forgets that the deliveries were made: what a relay finds that stopped after delivering and before
        recording it. The listeners then receive the events again - delivery is at least once."""
        for entry in self.entries:
            entry.delivered = False


@dataclasses.dataclass
class InboxTable:
    """The pairs (event, listener) received, as a transaction sees them."""

    received: set[Received] = dataclasses.field(default_factory=set)

    def add(self, received: Received) -> bool:
        """Records the pair; whether it is new."""
        if received in self.received:
            return False
        self.received.add(received)
        return True
