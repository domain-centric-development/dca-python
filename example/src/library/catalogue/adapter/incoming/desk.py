"""The catalogue desk: the catalogue's published entry, for staff and for other systems."""

from __future__ import annotations

import dataclasses

from dca_building_blocks import OpenHostService

from library.catalogue.application.acquire_copy import AcquireCopyCommand, AcquireCopyInputPort, TitleNotFound
from library.catalogue.application.register_title import RegisterTitleCommand, RegisterTitleInputPort, TitleNameInUse
from library.catalogue.domain.failure import BlankTitleName, CopyHeldAlready
from library.catalogue.domain.title import TitleName
from library.sharedkernel.domain.identity import TitleId


@dataclasses.dataclass(frozen=True)
class Created:
    """Entered: the new title's or copy's id, and for a copy its shelf mark."""

    id: int
    shelf_mark: str | None = None


@dataclasses.dataclass(frozen=True)
class Rejected:
    """Refused, with the reason's code."""

    reason: str


@dataclasses.dataclass(frozen=True)
class NotFound:
    """No such title."""


type DeskResponse = Created | Rejected | NotFound


class CatalogueDesk(OpenHostService, description="registers titles and acquires copies"):
    """The catalogue's open host service: registers titles and acquires copies."""

    def __init__(self, register: RegisterTitleInputPort, acquire: AcquireCopyInputPort) -> None:
        self._register = register
        self._acquire = acquire

    def register_title(self, name: str) -> DeskResponse:
        """Enters a title."""
        try:
            registered = self._register.execute(RegisterTitleCommand(TitleName(name)))
        except BlankTitleName:
            return Rejected("blank-name")
        except TitleNameInUse:
            return Rejected("name-taken")
        return Created(registered.title.value)

    def acquire_copy(self, title: int) -> DeskResponse:
        """Acquires a copy of a title."""
        try:
            acquired = self._acquire.execute(AcquireCopyCommand(TitleId(title)))
        except TitleNotFound:
            return NotFound()
        except CopyHeldAlready:
            return Rejected("copy-held-already")
        return Created(acquired.copy.value, acquired.shelf_mark.value)
