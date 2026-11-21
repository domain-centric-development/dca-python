from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import UseCase


@dataclasses.dataclass(frozen=True)
class RenamePartCommand:
    pass


class RenamePartContract(UseCase[RenamePartCommand, None], Protocol):  # DCA-NAM-003: not named *Port
    pass


class RenamePartUseCase(RenamePartContract):  # DCA-NAM-001: not named *Service
    def execute(self, command: RenamePartCommand) -> None:
        return None
