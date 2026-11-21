"""The relay: delivers the committed outbox entries to their listeners, at least once - the entries that share an
ordering key one after the other, the rest in parallel. Each listener runs its reaction in a transaction of its own."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dca_building_blocks import TransactionalEventListener

from library.sharedkernel.adapter.outgoing.memory import MemoryDatabase
from library.sharedkernel.adapter.outgoing.tables import OutboxEntry
from library.sharedkernel.application.shared import ListenerId


class Relay:
    """The relay of one store's outbox."""

    def __init__(self, database: MemoryDatabase[Any]) -> None:
        self._database = database
        self._routes: dict[ListenerId, Callable[[object], None]] = {}

    def route[E](self, event_type: type[E], listener_id: ListenerId, listener: TransactionalEventListener[E]) -> Relay:
        """Routes the entries registered for `listener_id` to the listener."""

        def deliver(payload: object) -> None:
            if not isinstance(payload, event_type):
                raise TypeError(f"the outbox holds a {type(payload).__name__} for {listener_id.name}")
            listener.on(payload)

        self._routes[listener_id] = deliver
        return self

    def deliver(self) -> int:
        """Delivers every entry still to make and records each delivery that succeeded. Answers how many were
        delivered, or raises the first failure - the failed entry and those after it with the same key stay in the
        outbox for the next run."""
        groups = in_order(self._database.undelivered())
        if not groups:
            return 0
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            running = [pool.submit(self._deliver_in_order, group) for group in groups]
        delivered = 0
        failures: list[BaseException] = []
        for future in running:
            failure = future.exception()
            if failure is None:
                delivered += future.result()
            else:
                failures.append(failure)
        if failures:
            raise failures[0]
        return delivered

    def _deliver_in_order(self, group: list[OutboxEntry]) -> int:
        for entry in group:
            route = self._routes.get(entry.listener)
            if route is None:
                raise LookupError(f"no listener routed for {entry.listener.name}")
            route(entry.payload)
            self._database.mark_delivered(entry.sequence)
        return len(group)


def in_order(entries: list[OutboxEntry]) -> list[list[OutboxEntry]]:
    """The entries grouped for delivery: one group per ordering key, in registration order, and one group per entry
    without a key."""
    keyed: dict[str, list[OutboxEntry]] = {}
    groups: list[list[OutboxEntry]] = []
    for entry in entries:
        if entry.order is None:
            groups.append([entry])
        else:
            keyed.setdefault(entry.order.key, []).append(entry)
    return groups + list(keyed.values())
