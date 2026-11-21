from __future__ import annotations

from dca_building_blocks import DomainEvent
from fx.sharedkernel.application.shared import Clock
from fx.sharedkernel.infrastructure import Settings


class MemoryOutbox:
    """The shared outbox: a technical adapter of the kernel's outgoing side, used by every context's publisher."""

    def __init__(self, settings: Settings) -> None:
        self._entries: list[tuple[DomainEvent, str]] = []
        self._limit = settings.limit

    def register(self, event: DomainEvent, listener: str, /) -> None:
        if len(self._entries) < self._limit:
            self._entries.append((event, listener))


class FixedClock(Clock):
    def now(self) -> str:
        return "2026-11-21T12:00:00Z"
