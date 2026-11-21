from __future__ import annotations

from dca_building_blocks import AggregateRoot, Factory, Id, Specification


class ThingId(Id):
    value: str


class Thing(AggregateRoot[ThingId]):
    """An aggregate root; the configured suffix selects by name only."""

    id: ThingId


class LedgerRoot:  # DCA-TAC-001: named by the configured aggregate-root suffix, without the role
    pass


class ThingFactory(Factory):  # DCA-ADV-013: not named by the configured factory suffix
    pass


class ThingMaker(Factory):
    """Named by the configured factory suffix."""


class OpenRule(Specification[Thing]):
    """Selected by the configured specification suffix and its role; it sits in the domain."""

    def is_satisfied_by(self, candidate: Thing) -> bool:
        return True
