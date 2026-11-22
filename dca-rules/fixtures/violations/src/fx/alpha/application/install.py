import typing

from dca_building_blocks import OutputPort


class Source(OutputPort, typing.Protocol):  # DCA-USE-023: declared here, used by check as well
    def read(self) -> int: ...


class OwnLog(OutputPort, typing.Protocol):
    def note(self) -> None: ...


class InstallUseCase:
    def __init__(self, source: Source, log: OwnLog) -> None:
        self.source = source
        self.log = log
