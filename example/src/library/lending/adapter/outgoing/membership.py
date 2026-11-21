"""The membership office, as lending asks it: a list of suspended members."""

from __future__ import annotations

from collections.abc import Iterable

from library.lending.domain.member import MemberId, MemberStandings, Standing


class SuspensionList(MemberStandings):
    """The members the office suspended; every other member is in good standing."""

    def __init__(self, suspended: Iterable[MemberId]) -> None:
        self._suspended = frozenset(suspended)

    def standing_of(self, member: MemberId, /) -> Standing:
        return Standing.SUSPENDED if member in self._suspended else Standing.GOOD
