from fx.alpha.domain.model import Label, Pricing

URL = "memory://"

PRICING = Pricing()  # the composition root may construct a domain service


def minimum() -> Label:
    return PRICING.price(Label("min"))  # DCA-ADV-021: but it does not call one
