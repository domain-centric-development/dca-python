"""The output ports more than one use case of the catalogue works with."""

from __future__ import annotations

from typing import Protocol

from dca_building_blocks import OutputPortException, Repository

from library.catalogue.domain.title import Title, TitleName
from library.sharedkernel.domain.identity import TitleId


class TitleNameTaken(OutputPortException):
    """Declared by `TitleRepository.add`: the catalogue holds a title of this name already."""

    def __init__(self, name: TitleName) -> None:
        super().__init__(f"the catalogue holds a title named {name.value!r} already")
        self.name = name


class TitleRepository(Repository[Title, TitleId], Protocol):
    """The titles of the catalogue."""

    def add(self, title: Title, /) -> Title:
        """Adds a new title. A name the catalogue holds already is refused with `TitleNameTaken` - only the store
        sees every name."""
        ...
