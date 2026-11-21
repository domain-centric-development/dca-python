from dca_building_blocks import IntegrationEvent


class KernelNoticed(IntegrationEvent, event_type="kernel.noticed", version=1):  # DCA-STR-007: never the kernel's
    event_id: str
    occurred_on: str
