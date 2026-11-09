from __future__ import annotations

from typing import Protocol

from dca_building_blocks import DomainGateway
from fx.alpha.domain.thing import ThingId


class Endorsements(DomainGateway, Protocol):
    def endorsed(self, thing_id: ThingId, /) -> bool: ...
