"""Publishes the catalogue's integration events: translated from its domain events inside the publishing transaction,
so they leave the context exactly when what caused them is committed."""

from __future__ import annotations

from dca_building_blocks import DomainEvent, EventListener, IntegrationEventPublisher

from library.catalogue.domain.title import CopyAcquired, TitleRegistered
from library.catalogue.events import CopyAcquired as CopyAcquiredEvent
from library.sharedkernel.application.shared import OrderingKey


class PublishCopyAcquired(EventListener[DomainEvent]):
    """Publishes a copy acquired to the other contexts. It reacts inside the transaction and calls an output port
    only: the integration event publisher, bound to the same transaction."""

    def __init__(self, publisher: IntegrationEventPublisher) -> None:
        self._publisher = publisher

    def on(self, event: DomainEvent, /) -> None:
        if isinstance(event, CopyAcquired):
            self._publisher.publish(
                CopyAcquiredEvent(event.event_id.value, event.occurred_on.value, event.title.value, event.copy.value)
            )


def by_title(event: DomainEvent) -> OrderingKey | None:
    """The catalogue's own deliveries are ordered per title."""
    match event:
        case TitleRegistered() | CopyAcquired():
            return OrderingKey(f"title-{event.title.value}")
        case _:
            return None
