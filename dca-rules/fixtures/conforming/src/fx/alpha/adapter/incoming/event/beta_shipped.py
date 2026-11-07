from fx.alpha.application.count_things import CountThingsInputPort, CountThingsQuery, TooFewThings
from fx.beta.api.events import BetaShipped


def on_beta_shipped(event: BetaShipped, port: CountThingsInputPort) -> None:
    try:
        port.execute(CountThingsQuery(0))
    except TooFewThings:
        return
