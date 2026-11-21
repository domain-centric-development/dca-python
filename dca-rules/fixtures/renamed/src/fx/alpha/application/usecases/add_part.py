from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import UseCase


@dataclasses.dataclass(frozen=True)
class AddPartCommand:
    pass


class AddPartPort(UseCase[AddPartCommand, None], Protocol):
    """Named by the configured input-port suffix; its module lies below an operation container."""


class AddPartService(AddPartPort):
    """Named by the configured use-case suffix; DCA-USE-014 measures it without the container."""

    def execute(self, command: AddPartCommand) -> None:
        return None
