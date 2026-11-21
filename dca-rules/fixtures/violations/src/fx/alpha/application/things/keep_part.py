import dataclasses
import typing

from dca_building_blocks import UseCase
from fx.alpha.application.add_part import AddPartResult
from fx.alpha.application.things.remove_part import RemovePartCommand


@dataclasses.dataclass(frozen=True)
class KeepPartCommand:
    part: str


class KeepPartInputPort(UseCase[KeepPartCommand, AddPartResult], typing.Protocol):
    pass


class KeepPartUseCase(KeepPartInputPort):
    def execute(self, command: KeepPartCommand, /) -> AddPartResult:
        RemovePartCommand(command.part)
        return AddPartResult()
