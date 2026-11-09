import typing

from dca_building_blocks import DomainGateway, OpenHostService

__dca__ = OpenHostService()  # DCA-STR-005: a module declares an open host service inside the domain


class Ratings(DomainGateway, typing.Protocol):  # DCA-PY-003: no class names the domain gateway
    def rating_of(self, key: str) -> bool: ...
