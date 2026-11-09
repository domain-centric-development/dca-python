from fx.alpha.application.add_part import AddPartInputPort  # DCA-HEX-013
from fx.alpha.application.shared import ThingRepository
from fx.alpha.domain.model import Label, Pricing
from fx.beta.adapter.outgoing import things as beta_store  # DCA-CYC-003
from fx.beta.infrastructure import WIRED  # DCA-HEX-005, DCA-STR-006
from fx.zeta.api import ZetaApi  # DCA-MAP-011: no upstream declared


class InMemory(ThingRepository):
    pass


class ShapeJournal:  # DCA-PY-003: fits JournalPort by its shape, names it nowhere
    def write(self, entry: Label) -> None:
        pass


class ShapePublisher:  # DCA-PY-003: fits DomainEventPublisher by its shape, names it nowhere
    def publish(self, event: object) -> None:
        pass


def export(pricing: Pricing, label: Label) -> Label:
    return pricing.price(label)  # DCA-ADV-021: an outgoing adapter computes with a domain service


class ShapeRatings:  # DCA-PY-003: fits the domain gateway Ratings by its shape, names it nowhere
    def rating_of(self, key: str) -> bool:
        return bool(key)
