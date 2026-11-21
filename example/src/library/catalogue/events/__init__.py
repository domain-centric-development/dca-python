"""The catalogue's integration events: their type and version are the contract, their fields plain data."""

from __future__ import annotations

import datetime
import uuid

from dca_building_blocks import IntegrationEvent


class CopyAcquired(IntegrationEvent, event_type="catalogue.copy-acquired", version=1):
    """The library acquired a copy of a title; it may be lent from now on."""

    event_id: uuid.UUID
    occurred_on: datetime.datetime
    title: int
    copy: int
