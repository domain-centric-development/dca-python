from dca_building_blocks import DomainEvent, EventListener
from fx.alpha.application.add_part import AddPartInputPort


class AddPartOnEvent(EventListener[DomainEvent]):  # DCA-HEX-017: drives a use case inside the transaction
    def __init__(self, port: AddPartInputPort) -> None:
        self._port = port

    def on(self, event: DomainEvent, /) -> None:
        return None
