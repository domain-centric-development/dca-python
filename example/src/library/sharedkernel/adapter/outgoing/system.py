"""The system's clock and a source of identities."""

from __future__ import annotations

import datetime
import itertools
import threading
import uuid

from dca_building_blocks import EventId, Timestamp

from library.sharedkernel.application.shared import Clock, IdSource


class SystemClock(Clock):
    """The operating system's clock."""

    def now(self) -> Timestamp:
        return Timestamp(datetime.datetime.now(datetime.UTC))


class SequentialIds(IdSource):
    """Identities counted up from one: unique within the process, which is all an in-memory store needs."""

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def next_id(self) -> int:
        with self._lock:
            return next(self._counter)

    def next_event_id(self) -> EventId:
        return EventId(uuid.UUID(int=self.next_id()))
