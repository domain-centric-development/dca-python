from __future__ import annotations

import dataclasses
import typing

from dca_building_blocks import UseCase
from fx.alpha.application.add_part import AddPartResult  # DCA-CYC-005


@dataclasses.dataclass(frozen=True)
class RemovePartCommand:
    part: str


class RemovePartInputPort(UseCase[RemovePartCommand, AddPartResult], typing.Protocol):
    pass


class RemovePartUseCase(RemovePartInputPort):  # DCA-USE-014: one level deeper than AddPartUseCase
    def execute(self, command: RemovePartCommand, /) -> AddPartResult:
        return AddPartResult()
