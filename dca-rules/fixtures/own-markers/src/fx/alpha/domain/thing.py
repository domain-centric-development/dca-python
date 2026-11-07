import dataclasses

from fx import markers
from fx.markers import AggregateRoot, Id


@dataclasses.dataclass(frozen=True)
class ThingId(Id):
    value: str


class Thing(AggregateRoot):
    def __init__(self, id: ThingId) -> None:
        self.id = id


@dataclasses.dataclass(frozen=True)
class Label(markers.Value):
    text: str
