from fx.alpha.application.shared import BetaLookup
from fx.alpha.domain.thing import ThingId
from fx.beta.api import BetaCatalog


class BetaCatalogLookup(BetaLookup):
    def __init__(self, catalog: BetaCatalog) -> None:
        self._catalog = catalog

    def known(self, thing_id: ThingId, /) -> bool:
        return self._catalog.knows(thing_id.value)
