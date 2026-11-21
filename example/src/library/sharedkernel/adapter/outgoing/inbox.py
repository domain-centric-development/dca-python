"""The inbox: which deliveries each listener has received, kept in the listener's transaction."""

from __future__ import annotations

from typing import Any

from library.sharedkernel.adapter.outgoing.memory import MemoryDatabase
from library.sharedkernel.application.shared import Delivery, Inbox, Received


class TransactionInbox(Inbox):
    """The inbox over the open transaction's table, so a pair is recorded only if the reaction commits."""

    def __init__(self, database: MemoryDatabase[Any]) -> None:
        self._database = database

    def receive(self, received: Received, /) -> Delivery:
        if self._database.staged().inbox.add(received):
            return Delivery.FIRST
        return Delivery.REPEATED
