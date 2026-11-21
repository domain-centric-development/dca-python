"""The library's shelf marks: the first letters of the name and the copy's number."""

from __future__ import annotations

from library.catalogue.domain.title import ShelfMark, ShelfMarks, TitleName
from library.sharedkernel.domain.identity import CopyId


class InitialsShelfMarks(ShelfMarks):
    """Shelves a copy under the first three letters of its title's name."""

    def mark_for(self, name: TitleName, copy: CopyId, /) -> ShelfMark:
        initials = "".join(c for c in name.value if c.isalnum())[:3]
        return ShelfMark(f"{initials.upper()}-{copy.value}")
