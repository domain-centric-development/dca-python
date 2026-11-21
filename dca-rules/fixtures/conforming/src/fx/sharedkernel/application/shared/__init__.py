from __future__ import annotations

from typing import Protocol

from dca_building_blocks import OutputPort


class Clock(OutputPort, Protocol):
    """A shared output port of the kernel's application layer."""

    def now(self) -> str: ...
