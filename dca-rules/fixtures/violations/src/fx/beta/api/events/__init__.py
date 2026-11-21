from dca_building_blocks import IntegrationEvent


class BetaRelisted(IntegrationEvent, event_type="beta.relisted", version=1):  # DCA-STR-007: events beside api
    event_id: str
    occurred_on: str
