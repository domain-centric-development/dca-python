from dca_building_blocks import IntegrationEvent


class BetaShipped(IntegrationEvent, event_type="beta.shipped", version=1):
    event_id: str
    occurred_on: str
    key: str
