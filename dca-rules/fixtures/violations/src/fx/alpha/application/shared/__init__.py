from __future__ import annotations

import typing

import sqlalchemy  # DCA-LAY-003: a framework in the application

from dca_building_blocks import (
    DomainEvent,
    DomainEventPublisher,
    DomainException,
    DomainService,
    Factory,
    OutputPort,
    PortException,
    Repository,
    Store,
)
from fx.alpha.adapter.outgoing.store import InMemory  # DCA-HEX-002
from fx.alpha.domain.model import Label, Thing, ThingId
from fx.alpha.infrastructure import config  # DCA-LAY-003
from fx.beta.application import BetaThing  # DCA-STR-003, DCA-CYC-002


class ThingRepository(Repository[Thing, ThingId], typing.Protocol):
    pass


class Lookup(typing.Protocol):  # DCA-HEX-009
    def look(self) -> None: ...


class LegacyRepository(typing.Protocol):  # DCA-TAC-013
    pass


class ThingsRepositoryPort(ThingRepository, typing.Protocol):  # DCA-NAM-004
    pass


class AuditStore(Repository[Thing, ThingId], typing.Protocol):  # DCA-TAC-018
    pass


class JournalPort(Store, typing.Protocol):
    def write(self, entry: Label) -> None: ...


class OrphanPort(OutputPort, typing.Protocol):  # DCA-PY-003: nobody names it
    def ping(self) -> None: ...


class LooseRepository:  # DCA-HEX-008
    pass


class AppThingRepository(ThingRepository):  # DCA-TAC-015
    pass


class AppStore(JournalPort):  # DCA-TAC-020
    def write(self, entry: Label) -> None:
        pass


class AppPublisher(DomainEventPublisher):  # DCA-HEX-019
    def publish(self, event: DomainEvent, /) -> None:
        pass


class Unhappy(Exception):  # DCA-ERR-003
    pass


class Classified(PortException):  # DCA-ERR-003: a classification, not a leaf
    pass


class ThingRejected(DomainException):  # DCA-ERR-002
    pass


class AppEvent(DomainEvent):  # DCA-ADV-002
    pass


class AppService(DomainService):  # DCA-ADV-010
    pass


class AppFactory(Factory):  # DCA-ADV-014
    pass


class AppSpecification:  # DCA-ADV-017
    pass


class ReportDto:  # DCA-USE-011
    pass


class LabelConverter:  # DCA-NAM-008
    pass


class ThingViewModel:  # DCA-NAM-011
    pass


class FooResponse:  # DCA-USE-008
    pass
