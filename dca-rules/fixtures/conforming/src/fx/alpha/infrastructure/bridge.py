from dca_building_blocks import DomainEvent, DomainEventPublisher
from fx.alpha.application.count_things import CountThingsInputPort, CountThingsQuery, TooFewThings


class CountingPublisher(DomainEventPublisher):
    """A context's wiring that hands the events to a second use case: no output port's implementation (DCA-HEX-019)."""

    def __init__(self, port: CountThingsInputPort) -> None:
        self._port = port

    def publish(self, event: DomainEvent, /) -> None:
        try:
            self._port.execute(CountThingsQuery(0))
        except TooFewThings:
            return
