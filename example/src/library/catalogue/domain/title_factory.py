"""Enters a new title into the catalogue."""

from __future__ import annotations

from dca_building_blocks import EventId, Factory, Timestamp

from library.catalogue.domain.title import Title, TitleName
from library.sharedkernel.domain.identity import TitleId


class TitleFactory(Factory):
    """Enters a new title into the catalogue: the title starts without holdings and records its registration."""

    def register(self, title: TitleId, name: TitleName, event_id: EventId, at: Timestamp) -> Title:
        """A newly registered title."""
        return Title.register(title, name, event_id, at)
