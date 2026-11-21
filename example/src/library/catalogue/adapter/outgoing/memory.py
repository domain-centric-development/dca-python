"""The catalogue's tables in the kernel's in-memory store."""

from __future__ import annotations

import dataclasses

from library.catalogue.application.shared import TitleNameTaken, TitleRepository
from library.catalogue.domain.title import Title
from library.sharedkernel.adapter.outgoing.memory import MemoryDatabase
from library.sharedkernel.domain.identity import TitleId


@dataclasses.dataclass
class CatalogueTables:
    """The catalogue's tables."""

    titles: dict[TitleId, Title] = dataclasses.field(default_factory=dict)


class MemoryTitleRepository(TitleRepository):
    """The titles as the open transaction sees them."""

    def __init__(self, database: MemoryDatabase[CatalogueTables]) -> None:
        self._database = database

    def _titles(self) -> dict[TitleId, Title]:
        return self._database.staged().tables.titles

    def find_by_id(self, aggregate_id: TitleId, /) -> Title | None:
        return self._titles().get(aggregate_id)

    def save(self, aggregate: Title, /) -> Title:
        self._titles()[aggregate.id] = aggregate
        return aggregate

    def delete_by_id(self, aggregate_id: TitleId, /) -> None:
        self._titles().pop(aggregate_id, None)

    def add(self, title: Title, /) -> Title:
        if any(held.name == title.name for held in self._titles().values()):
            raise TitleNameTaken(title.name)
        return self.save(title)
