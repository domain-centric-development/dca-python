from dca_building_blocks import TransactionalEventListener
from fx.alpha.application.count_things import CountThingsInputPort, CountThingsQuery, TooFewThings
from fx.beta.events import BetaShipped


def on_beta_shipped(event: BetaShipped, port: CountThingsInputPort) -> None:
    try:
        port.execute(CountThingsQuery(0))
    except TooFewThings:
        return


class CountOnBetaShipped(TransactionalEventListener[BetaShipped]):
    """Drives an input port after the commit, in a transaction of its own (DCA-HEX-017)."""

    def __init__(self, port: CountThingsInputPort) -> None:
        self._port = port

    def on(self, event: BetaShipped, /) -> None:
        on_beta_shipped(event, self._port)
