"""A title of the catalogue and its holdings - the copies the library acquired of it."""

from __future__ import annotations

from typing import Protocol

from dca_building_blocks import AggregateRoot, DomainEvent, DomainGateway, Entity, EventId, Timestamp, Value

from library.catalogue.domain.failure import BlankTitleName, CopyHeldAlready
from library.sharedkernel.domain.identity import CopyId, TitleId


class TitleName(Value):
    """The name a title is catalogued under, trimmed, never blank."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise BlankTitleName()
        object.__setattr__(self, "value", self.value.strip())


class ShelfMark(Value):
    """Where a copy stands on the shelves."""

    value: str


class ShelfMarks(DomainGateway, Protocol):
    """Assigns the shelf mark of a new copy - the library's classification scheme, computed outside the model: a
    domain gateway, which the title receives as a parameter."""

    def mark_for(self, name: TitleName, copy: CopyId, /) -> ShelfMark:
        """The mark of a copy of the title with this name."""
        ...


class TitleRegistered(DomainEvent):
    """A title entered the catalogue."""

    event_id: EventId
    occurred_on: Timestamp
    title: TitleId
    name: TitleName


class CopyAcquired(DomainEvent):
    """The library acquired a copy of a title."""

    event_id: EventId
    occurred_on: Timestamp
    title: TitleId
    copy: CopyId
    shelf_mark: ShelfMark


class Holding(Entity[CopyId]):
    """A copy the library holds of a title, where it stands on the shelves."""

    def __init__(self, copy: CopyId, shelf_mark: ShelfMark) -> None:
        self._id = copy
        self._shelf_mark = shelf_mark

    @property
    def id(self) -> CopyId:
        return self._id

    @property
    def shelf_mark(self) -> ShelfMark:
        return self._shelf_mark


class Title(AggregateRoot[TitleId]):
    """A title of the catalogue: the aggregate root over its holdings."""

    def __init__(self, title: TitleId, name: TitleName, holdings: list[Holding]) -> None:
        self._id = title
        self._name = name
        self._holdings = holdings

    @classmethod
    def register(cls, title: TitleId, name: TitleName, event_id: EventId, at: Timestamp) -> Title:
        """A title entered into the catalogue, without holdings yet; it records its registration."""
        registered = cls(title, name, [])
        registered.register_event(TitleRegistered(event_id, at, title, name))
        return registered

    @property
    def id(self) -> TitleId:
        return self._id

    @property
    def name(self) -> TitleName:
        return self._name

    def holdings(self) -> tuple[Holding, ...]:
        """The copies acquired of it."""
        return tuple(self._holdings)

    def acquire_copy(self, marks: ShelfMarks, copy: CopyId, event_id: EventId, at: Timestamp) -> ShelfMark:
        """Adds a copy the library acquired, shelved under the mark the classification gives it."""
        if any(holding.id == copy for holding in self._holdings):
            raise CopyHeldAlready()
        shelf_mark = marks.mark_for(self._name, copy)
        self._holdings.append(Holding(copy, shelf_mark))
        self.register_event(CopyAcquired(event_id, at, self._id, copy, shelf_mark))
        return shelf_mark
