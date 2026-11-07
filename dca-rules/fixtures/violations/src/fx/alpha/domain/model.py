from __future__ import annotations

import asyncio  # DCA-PY-004
import dataclasses
import datetime
import enum
import random
import typing

import fastapi
import payments_sdk  # DCA-ONI-002, DCA-MAP-010
import pydantic
import sqlalchemy.orm

from dca_building_blocks import (
    AggregateRoot,
    Consumes,
    DomainEvent,
    DomainException,
    DomainService,
    Entity,
    Factory,
    Id,
    IntegrationEvent,
    OpenHostService,
    Owned,
    Repository,
    Specification,
    Store,
    Timestamp,
    TransactionBoundary,
    Translation,
    Upstream,
    UseCaseException,
    Value,
)
from fx.alpha.adapter.outgoing.store import InMemory  # DCA-HEX-001
from fx.alpha.application.shared import ThingRepository  # DCA-ONI-001
from fx.alpha.infrastructure import config  # DCA-LAY-002
from fx.beta.api import BetaApi  # DCA-STR-004, DCA-MAP-009 (conformist)
from fx.beta.domain.model import BetaModel  # DCA-STR-004, DCA-CYC-001

DECLARED_HERE = Upstream(context="beta", translation=Translation.CONFORMIST, via=(Consumes.API,))  # DCA-MAP-001


class ThingId(Id):
    value: str


class OtherId(Id):
    value: str


class PartId(Id):
    value: str


class Status(enum.Enum):
    OPEN = "open"


class OrderAggregateRoot:  # DCA-TAC-001
    pass


class Thing(AggregateRoot[ThingId], Owned):  # DCA-TAC-026: Owned without the owner's id type
    def __init__(self, thing_id: ThingId, repo: ThingRepository, other: Other, count: int) -> None:
        self._id = thing_id
        self.repo = repo  # DCA-TAC-002
        self.other = other  # DCA-TAC-003
        self.count = count  # DCA-TAC-025
        self.parent: Thing | None = None  # DCA-TAC-003: another aggregate of its own type

    @property
    def id(self) -> ThingId:
        return self._id

    def set_label(self, label: Label) -> None:  # DCA-TAC-006
        self.label = label


class Other(AggregateRoot[OtherId]):  # DCA-TAC-004: no field holds its id
    @property
    def id(self) -> OtherId:
        return OtherId("computed")


@dataclasses.dataclass  # DCA-PY-002
class Part(Entity[PartId]):
    part_id: PartId
    owner: Thing  # DCA-TAC-007

    @property
    def id(self) -> PartId:
        return self.part_id

    def __eq__(self, other: object) -> bool:  # DCA-PY-002
        return False

    def price(self) -> Label:
        return Pricing().price(Label("x"))  # DCA-ADV-019


@dataclasses.dataclass(frozen=True)  # DCA-PY-001: a value carries no decorator of its own
class Label(Value):
    value: str
    items: list[str] = dataclasses.field(default_factory=list)  # DCA-TAC-010
    part: Part | None = None  # DCA-TAC-008

    def set_value(self, value: Label) -> None:  # DCA-TAC-011, DCA-TAC-006
        object.__setattr__(self, "value", value.value)  # DCA-TAC-010

    def __eq__(self, other: object) -> bool:  # DCA-TAC-012
        return True

    @classmethod
    def of(cls, raw: Label) -> Label:  # DCA-TAC-024
        return raw

    @classmethod
    def from_raw(cls, raw: Label) -> Label:
        return raw


class SpecialLabel(Label):  # DCA-TAC-009
    pass


@dataclasses.dataclass  # DCA-PY-001: a mutable dataclass in the domain
class Record:
    label: Label


class PartRepository(Repository[Part, PartId], typing.Protocol):  # DCA-TAC-014, DCA-TAC-016, DCA-HEX-010
    def parts(self) -> list[Part]: ...  # DCA-TAC-017


class JournalStore(Store, typing.Protocol):  # DCA-TAC-019
    def save(self, label: Label) -> None: ...  # DCA-TAC-021


class ThingChanged(DomainEvent):  # DCA-ADV-008: no timestamp
    tags: list[Label]  # DCA-ADV-001
    schema_version: Label  # DCA-ADV-007
    label: Label = pydantic.Field()  # DCA-ADV-004, DCA-ONI-003


class ThingEvent:  # DCA-ADV-001: named an event, no DomainEvent
    pass


@sqlalchemy.orm.declarative_mixin  # DCA-ADV-011
class Pricing(DomainService):
    def price(self, label: Label) -> Label:  # DCA-ADV-020
        return label

    def remember(self, label: Label) -> None:
        self.last = label  # DCA-ADV-012


@sqlalchemy.orm.declarative_mixin  # DCA-ADV-015
class Builder(Factory):  # DCA-ADV-013
    def build(self, label: Label) -> None:
        self.last = label  # DCA-ADV-016


@sqlalchemy.orm.declarative_mixin  # DCA-ADV-018
class CheapSpecification(Specification[Thing]):
    def is_satisfied_by(self, candidate: Thing) -> bool:
        return True


class StringHelper:  # DCA-NAM-010
    pass


class ThingDto:  # DCA-USE-010, DCA-NAM-007
    pass


class StrayCommand:  # DCA-USE-002
    pass


class StrayQuery:  # DCA-USE-003
    pass


class StrayResult:  # DCA-USE-006
    pass


class BadFailure(Exception):  # DCA-ERR-001
    pass


class DomainSideFailure(UseCaseException):  # DCA-ERR-002: a port exception in the domain
    pass


class HttpThingRejected(DomainException, fastapi.HTTPException):  # DCA-ERR-004, DCA-ERR-005
    def __init__(self, message: str) -> None:
        self.message = message  # DCA-ERR-007


class ThingFull(DomainException):
    pass


class AlphaHost(OpenHostService):  # DCA-STR-005
    pass


class AlphaShipped(IntegrationEvent, event_type="alpha.shipped"):  # DCA-STR-007
    schema_version: Label  # DCA-ADV-006
    tags: list[Label]  # DCA-STR-008


class Untyped(IntegrationEvent):  # DCA-ADV-005
    pass


class Txn:
    boundary: TransactionBoundary  # DCA-LAY-004


def now_label() -> Label:
    datetime.datetime.now()  # DCA-PY-005
    random.random()  # DCA-PY-005
    return Label("x")


async def fetch() -> None:  # DCA-PY-004
    await asyncio.sleep(0)
