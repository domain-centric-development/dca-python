from __future__ import annotations

from typing import Protocol

from dca_building_blocks import Repository
from fx.alpha.domain.thing import Thing, ThingId


class ThingRepo(Repository[Thing, ThingId], Protocol):
    """Named by the configured repository suffix: DCA-NAM-004 and DCA-TAC-016 pass it."""


class ThingRepoIndex(Protocol):  # DCA-NAM-004: names a repository by the suffix but does not end with it
    pass
