from __future__ import annotations

from typing import Protocol

from dca_building_blocks import DomainGateway
from fx.alpha.domain.thing import ThingId


class Endorsements(DomainGateway, Protocol):
    def endorsed(self, thing_id: ThingId, /) -> bool: ...


class Ratings(DomainGateway, Protocol):
    """A domain gateway may answer asynchronously when its adapter does (DCA-ONI-004)."""

    async def endorsed_later(self, thing_id: ThingId, /) -> bool: ...
