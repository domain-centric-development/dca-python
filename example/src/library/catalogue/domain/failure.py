"""What the catalogue refuses."""

from dca_building_blocks import DomainException


class BlankTitleName(DomainException):
    """A title needs a name."""

    def __init__(self) -> None:
        super().__init__("a title needs a name")


class CopyHeldAlready(DomainException):
    """The title holds this copy already."""

    def __init__(self) -> None:
        super().__init__("the title holds this copy already")
