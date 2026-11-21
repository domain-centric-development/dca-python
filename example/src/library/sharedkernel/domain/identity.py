"""The identities both contexts speak of."""

from dca_building_blocks import Id


class TitleId(Id):
    """A title the library holds - a book, whatever number of copies it has."""

    value: int


class CopyId(Id):
    """One physical copy of a title."""

    value: int
