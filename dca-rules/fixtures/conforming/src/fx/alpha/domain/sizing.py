from __future__ import annotations

from dca_building_blocks import DomainService, Factory, Specification
from fx.alpha.domain.thing import Thing, ThingId
from fx.sharedkernel.domain.owner import OwnerId


class Balancing(DomainService):
    def balanced(self, first: Thing, second: Thing) -> bool:
        return first.is_full() == second.is_full()


class ThingFactory(Factory):
    def fresh(self, thing_id: ThingId, owner: OwnerId) -> Thing:
        return Thing.create(thing_id, owner)


class FullThingSpecification(Specification[Thing]):
    def is_satisfied_by(self, candidate: Thing) -> bool:
        return candidate.is_full()
