"""Shelves the copies the catalogue acquired: reacts after the catalogue committed, delivered from its outbox, and
drives a use case that runs in a transaction of its own. The catalogue's event is translated here into lending's
terms."""

from __future__ import annotations

from dca_building_blocks import EventId, TransactionalEventListener

from library.catalogue.events import CopyAcquired
from library.lending.application.shelve_copy import ShelveCopyCommand, ShelveCopyInputPort
from library.sharedkernel.application.shared import ListenerId, Received
from library.sharedkernel.domain.identity import CopyId, TitleId

#: The stable name of the listener that shelves the copies the catalogue acquired.
SHELVE_ACQUIRED_COPY = ListenerId("lending.shelve-acquired-copy")


class ShelveAcquiredCopy(TransactionalEventListener[CopyAcquired]):
    """Puts every copy the catalogue acquired on lending's shelf."""

    def __init__(self, shelve: ShelveCopyInputPort) -> None:
        self._shelve = shelve

    def on(self, event: CopyAcquired, /) -> None:
        received = Received(EventId(event.event_id), SHELVE_ACQUIRED_COPY)
        self._shelve.execute(ShelveCopyCommand(received, CopyId(event.copy), TitleId(event.title)))
