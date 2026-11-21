from __future__ import annotations

import abc
from typing import Protocol

from dca_building_blocks import OutputPortException, Repository, Store
from fx.alpha.domain.thing import Thing, ThingId
from fx.sharedkernel.domain.owner import OwnerId


class ThingRepository(Repository[Thing, ThingId], Protocol):
    def find_for_owner(self, thing_id: ThingId, owner: OwnerId, /) -> Thing | None: ...


class ThingJournal(Store, Protocol):
    def record(self, thing_id: ThingId, /) -> None: ...

    def count(self) -> int: ...


class Tally(Store, Protocol):
    def count(self) -> int: ...


class BetaLookup(Store, Protocol):
    def known(self, thing_id: ThingId, /) -> bool: ...


class BetaUnavailable(OutputPortException):
    pass


class RepositoryUnavailable(OutputPortException):
    """A failure named after the repository it concerns: no repository port (DCA-NAM-004 selects interfaces)."""


class Ledger(Store, abc.ABC):
    """An abstract base class with abstract methods only is a port, as a Protocol is (DCA-TAC-020, DCA-HEX-019)."""

    @abc.abstractmethod
    def entries(self) -> int: ...
