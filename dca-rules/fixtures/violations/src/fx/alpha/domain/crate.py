"""Cases the rules read beyond the obvious: fields outside __init__ and in role-less bases, abstract base classes as
ports, nested classes, framework metadata on methods and parameters, and builds that are no plain call."""

import abc
import dataclasses
import datetime
import enum
import typing

import fastapi
import pydantic
from vendor import ledger  # DCA-MAP-010: the contract vendor.ledger, imported from its package

from dca_building_blocks import AggregateRoot, Entity, Id, Repository, Value
from fx.alpha.domain.model import Label, Other, Part, Pricing, Thing


class CrateId(Id):
    value: str


class TileId(Id):
    value: str


class Holding:
    """A base without a role: what it holds and does is its subclasses' own."""

    def __init__(self, other: Other) -> None:
        self.held = other  # DCA-TAC-003: a field of a role-less base

    def set_note(self, note: Label) -> None:  # DCA-TAC-006: a setter of a role-less base
        self.note = note


class Crate(Holding, AggregateRoot[CrateId]):
    def __init__(self, crate_id: CrateId, other: Other) -> None:
        super().__init__(other)
        self._id = crate_id

    @property
    def id(self) -> CrateId:
        return self._id

    def link(self, other: Other) -> None:
        self.linked = other  # DCA-TAC-003: a field first held outside __init__


class Ledger(Repository[Crate, CrateId], abc.ABC):  # DCA-TAC-014: an abstract base class is a port as well
    @abc.abstractmethod
    def crates(self) -> list[Crate]: ...


class Shelf:
    class Slot(Value):  # a nested class is a class of its own
        items: list[Label]  # DCA-TAC-010


class Gauge:
    reading: typing.Annotated[Label, pydantic.Field()]  # DCA-ONI-003: metadata in Annotated

    def __init__(self, source: Label = fastapi.Depends(Label)) -> None:  # DCA-ONI-003: a framework default
        self._source = source

    @pydantic.validator("reading")  # DCA-ONI-003: a framework decorator on a method
    def checked(self, reading: Label) -> Label:
        return reading


class Broken(ValueError):  # DCA-ERR-001: a built-in exception subclass in the domain
    pass


class Latch(enum.Enum):  # DCA-TAC-025: an adjective-like state and its negation
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class Shade(enum.Enum):
    RED = "red"

    def code(self) -> str:  # DCA-TAC-025: an enum's method is read like any other
        return self.value


class Scale:
    def __init__(self, unit: Label) -> None:
        self._unit = unit

    def _weigh(self, grams: int) -> Label:  # DCA-TAC-025: a private method is read as well
        return self._unit


class Size(Value):
    label: Label
    other: Label

    @staticmethod
    def of(raw: Label) -> "Size":  # DCA-TAC-024: a static factory takes what parsed takes
        return Size(raw, raw)

    @staticmethod
    def parsed(raw: Label) -> "Size":
        return Size(raw, raw)


class ShelfCommand(Value):  # DCA-USE-002: a value named a command is a command
    label: Label


class Tile(Entity[TileId]):
    def __init__(self, tile_id: TileId) -> None:
        self._id = tile_id

    @property
    def id(self) -> TileId:
        return self._id

    def priced(self, pricing: Pricing) -> Label:
        return pricing.price(Label("x"))  # DCA-ADV-019: calls the domain service it was handed


def loose_part() -> Part:
    return Part(None, None)  # DCA-TAC-005: a domain function, no aggregate, entity or factory


def renamed(thing: Thing) -> Thing:
    return dataclasses.replace(thing)  # DCA-TAC-023: a copy is a build


def stored(session: typing.Any, since: datetime.timedelta) -> None:
    with session.begin():  # DCA-LAY-004: a transaction run in the domain
        pass
