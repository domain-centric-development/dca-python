from fx.alpha.application.common import ThingRepo
from fx.alpha.domain.thing import Thing, ThingId


class InMemoryThingRepo(ThingRepo):
    """In the configured outgoing package: DCA-HEX-008 passes it."""

    def find_by_id(self, thing_id: ThingId, /) -> Thing | None:
        return None

    def save(self, thing: Thing, /) -> None:
        return None

    def delete_by_id(self, thing_id: ThingId, /) -> None:
        return None
