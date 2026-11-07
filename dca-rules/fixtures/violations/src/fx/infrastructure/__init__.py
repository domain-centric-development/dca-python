from dca_building_blocks import DomainEvent, DomainEventPublisher
from fx.alpha.adapter.incoming.web.things import router


class RootPublisher(DomainEventPublisher):  # DCA-HEX-019: drives no input port
    def publish(self, event: DomainEvent, /) -> None:
        print(event)


@router.get("/health")
def health() -> str:  # DCA-HEX-018: a handler in the composition root
    return "ok"
