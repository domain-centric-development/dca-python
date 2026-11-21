from dca_building_blocks import DomainEvent, DomainEventPublisher
from fx.alpha.application.add_part import AddPartInputPort


class Bridge(DomainEventPublisher):
    """Hands the events to a second use case: wiring, not an output port's implementation."""

    def __init__(self, port: AddPartInputPort) -> None:
        self._port = port

    def publish(self, event: DomainEvent, /) -> None:
        self._port.execute(None)


class Loose(DomainEventPublisher):  # DCA-HEX-019: beside a bridge, it drives no input port itself
    def publish(self, event: DomainEvent, /) -> None:
        print(event)
