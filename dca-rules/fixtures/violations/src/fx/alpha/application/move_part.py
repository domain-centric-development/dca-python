import typing

from dca_building_blocks import UseCase
from fx.alpha.application.add_part import AddPartCommand, AddPartResult


class MovePartInputPort(UseCase[AddPartCommand, AddPartResult], typing.Protocol):  # DCA-PY-008: nobody names it
    pass


class MovePartUseCase:  # DCA-PY-008: executes a use case and names no input port
    def execute(self, command: AddPartCommand, /) -> AddPartResult:
        raise NotImplementedError
