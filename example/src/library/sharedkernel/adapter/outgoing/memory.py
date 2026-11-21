"""A store in memory with transactions: a transaction works on a copy of the tables and replaces them on commit; one
transaction runs at a time."""

from __future__ import annotations

import contextvars
import copy
import dataclasses
import threading
from collections.abc import Callable

from dca_building_blocks import TransactionBoundary

from library.sharedkernel.adapter.outgoing.tables import InboxTable, OutboxEntry, OutboxTable


@dataclasses.dataclass
class Staged[C]:
    """A context's tables with the kernel's outbox and inbox beside them, so an aggregate and the deliveries its
    events owe are committed together."""

    tables: C
    outbox: OutboxTable = dataclasses.field(default_factory=OutboxTable)
    inbox: InboxTable = dataclasses.field(default_factory=InboxTable)


class MemoryDatabase[C](TransactionBoundary):
    """The in-memory store of one context, and its transaction boundary. The adapters bound to it read and write
    the copy of the open transaction; outside a transaction they have nothing to work on."""

    def __init__(self, tables: C) -> None:
        self._committed = Staged(tables)
        self._lock = threading.Lock()
        self._open: contextvars.ContextVar[Staged[C] | None] = contextvars.ContextVar(
            f"transaction-{id(self)}", default=None
        )

    def in_transaction[T](self, work: Callable[[], T], /) -> T:
        with self._lock:
            staged = copy.deepcopy(self._committed)
            token = self._open.set(staged)
            try:
                result = work()
            finally:
                self._open.reset(token)
            self._committed = staged
            return result

    def staged(self) -> Staged[C]:
        """The tables as the open transaction sees them."""
        staged = self._open.get()
        if staged is None:
            raise RuntimeError("the store is used outside a transaction")
        return staged

    def read[R](self, query: Callable[[Staged[C]], R], /) -> R:
        """Reads the committed tables."""
        with self._lock:
            return query(self._committed)

    def undelivered(self) -> list[OutboxEntry]:
        """The committed deliveries still to make."""
        return self.read(lambda staged: list(staged.outbox.undelivered()))

    def mark_delivered(self, sequence: int) -> None:
        with self._lock:
            self._committed.outbox.mark_delivered(sequence)

    def forget_deliveries(self) -> None:
        """Forgets the deliveries the relay made - see `OutboxTable.forget_deliveries`."""
        with self._lock:
            self._committed.outbox.forget_deliveries()
