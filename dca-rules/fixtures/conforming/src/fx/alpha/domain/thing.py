from __future__ import annotations

import enum

from dca_building_blocks import (
    AggregateRoot,
    DomainEvent,
    DomainException,
    Entity,
    EventId,
    Id,
    Owned,
    Timestamp,
    Value,
)
from fx.sharedkernel.domain.owner import OwnerId

LIMIT = 3


class ThingId(Id):
    value: str


class Side(enum.Enum):
    """Two cases with names of their own: no boolean in disguise (DCA-TAC-025)."""

    LEFT = "left"
    RIGHT = "right"


class PartId(Id):
    value: str


class Label(Value):
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("a label is not blank")


class PartAdded(DomainEvent):
    event_id: EventId
    occurred_on: Timestamp
    thing_id: ThingId
    part_id: PartId


class ThingFull(DomainException):
    def __init__(self, thing_id: ThingId) -> None:
        super().__init__(f"{thing_id} holds {LIMIT} parts")
        self.thing_id = thing_id


class Part(Entity[PartId]):
    def __init__(self, part_id: PartId, label: Label) -> None:
        self._id = part_id
        self._label = label

    @property
    def id(self) -> PartId:
        return self._id

    def relabel(self, label: Label) -> None:
        self._label = label


class Thing(AggregateRoot[ThingId], Owned[OwnerId]):
    def __init__(self, thing_id: ThingId, owner: OwnerId, parts: list[Part], archived: bool = False) -> None:
        self._id = thing_id
        self._owner = owner
        self._parts = parts
        self._archived = archived

    @classmethod
    def create(cls, thing_id: ThingId, owner: OwnerId) -> Thing:
        return cls(thing_id, owner, [])

    @classmethod
    def reconstitute(cls, thing_id: ThingId, owner: OwnerId, parts: list[Part], archived: bool) -> Thing:
        """Rebuilds a stored thing; its yes/no fact comes back as the bool it was."""
        return cls(thing_id, owner, parts, archived)

    @property
    def id(self) -> ThingId:
        return self._id

    def is_full(self) -> bool:
        return len(self._parts) >= LIMIT

    def add_part(self, part_id: PartId, label: Label, event_id: EventId, now: Timestamp) -> None:
        if self.is_full():
            raise ThingFull(self._id)
        self._parts.append(Part(part_id, label))
        self.register_event(PartAdded(event_id, now, self._id, part_id))
