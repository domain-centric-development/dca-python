"""What lending refuses."""

from dca_building_blocks import DomainException


class NotOnShelf(DomainException):
    """The copy is out on loan."""

    def __init__(self) -> None:
        super().__init__("the copy is out on loan")


class NotOnLoan(DomainException):
    """The copy is on the shelf, there is nothing to return."""

    def __init__(self) -> None:
        super().__init__("the copy is not on loan")


class ReservationClosed(DomainException):
    """The reservation was fulfilled already."""

    def __init__(self) -> None:
        super().__init__("the reservation was fulfilled already")
