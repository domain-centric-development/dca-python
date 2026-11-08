from fx.alpha.adapter.outgoing.memory import DirectTransactions, InMemoryThingRepository, ListJournal, ListPublisher
from fx.alpha.application.add_part import AddPartInputPort, AddPartUseCase
from fx.alpha.application.count_things import CountThingsInputPort, CountThingsUseCase
from fx.alpha.domain.sizing import Balancing, Pairing


def add_part() -> AddPartInputPort:
    return AddPartUseCase(InMemoryThingRepository(), ListPublisher(), DirectTransactions())


def count_things() -> CountThingsInputPort:
    return CountThingsUseCase(ListJournal())


def pairing() -> Pairing:
    """The composition root builds the domain services (DCA-ADV-021); it calls none of them."""
    return Pairing(Balancing())

