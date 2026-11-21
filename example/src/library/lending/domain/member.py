"""The members of the library, as lending knows them."""

from __future__ import annotations

import enum
from typing import Protocol

from dca_building_blocks import DomainGateway, Id


class MemberId(Id):
    """A member of the library."""

    value: int


class Standing(enum.Enum):
    """Whether a member may borrow."""

    GOOD = "good"
    SUSPENDED = "suspended"


class MemberStandings(DomainGateway, Protocol):
    """The members' standing, kept by the membership office - a fact lending does not hold: a domain gateway the
    terms of lending ask."""

    def standing_of(self, member: MemberId, /) -> Standing:
        """The member's standing today."""
        ...
