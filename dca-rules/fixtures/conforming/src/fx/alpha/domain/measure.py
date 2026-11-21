from __future__ import annotations

import datetime
import enum

from dca_building_blocks import Timestamp, Value


class Latch(enum.Enum):
    """Two actions, no fact and its negation (DCA-TAC-025)."""

    LOCK = "lock"
    UNLOCK = "unlock"


class Grams(Value):
    """A wrapper whatever its one field is called (DCA-TAC-025)."""

    amount: int


class Window(Value):
    """A span of time passes, as Java's Duration does (DCA-TAC-025)."""

    start: Timestamp
    length: datetime.timedelta
