"""The library's terms of lending."""

from __future__ import annotations

from dca_building_blocks import DomainService

from library.lending.domain.copy import LendableCopy
from library.lending.domain.loan import LoanPeriod
from library.lending.domain.member import MemberId, MemberStandings, Standing

#: How many loans make a copy popular, with a shorter period.
POPULAR_AFTER = 3


class LoanTerms(DomainService):
    """The library's terms of lending: how long a member may keep a copy, if at all. It asks the membership office
    for the member's standing through the domain gateway it holds."""

    def __init__(self, regular: LoanPeriod, standings: MemberStandings) -> None:
        self._regular = regular
        self._standings = standings

    def period_for(self, copy: LendableCopy, member: MemberId) -> LoanPeriod | None:
        """The period the member may keep the copy, or nothing for a suspended member. A popular copy goes out for
        half the period."""
        if self._standings.standing_of(member) is Standing.SUSPENDED:
            return None
        if len(copy.loans()) >= POPULAR_AFTER:
            return self._regular.halved()
        return self._regular
