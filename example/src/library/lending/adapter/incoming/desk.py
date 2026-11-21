"""The lending desk: members borrow, return and reserve copies here."""

from __future__ import annotations

import dataclasses
from typing import assert_never

from library.lending.application.lend_copy import (
    CopyNotOnShelf,
    LendCopyCommand,
    LendCopyInputPort,
    Lent,
    LoanLimitReached,
    MemberSuspended,
)
from library.lending.application.reserve_copy import ReserveCopyCommand, ReserveCopyInputPort, Reserved
from library.lending.application.return_copy import CopyNotOnLoan, ReturnCopyCommand, ReturnCopyInputPort, Returned
from library.lending.application.shared import UnknownCopy
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import ReservationId
from library.sharedkernel.domain.identity import CopyId


@dataclasses.dataclass(frozen=True)
class Done:
    """Done: the new loan's or reservation's id, or the copy returned."""

    id: int


@dataclasses.dataclass(frozen=True)
class Refused:
    """Refused, with the reason's code."""

    reason: str


type DeskResponse = Done | Refused


class LendingDesk:
    """The desk over lending's input ports."""

    def __init__(self, lend: LendCopyInputPort, give_back: ReturnCopyInputPort, reserve: ReserveCopyInputPort) -> None:
        self._lend = lend
        self._give_back = give_back
        self._reserve = reserve

    def lend(self, member: int, copy: int, reservation: int | None = None) -> DeskResponse:
        """A member borrows a copy, collecting their reservation if they name one."""
        collected = None if reservation is None else ReservationId(reservation)
        result = self._lend.execute(LendCopyCommand(CopyId(copy), MemberId(member), collected))
        match result:
            case Lent(loan=loan):
                return Done(loan.value)
            case UnknownCopy():
                return Refused("unknown-copy")
            case CopyNotOnShelf():
                return Refused("not-on-shelf")
            case MemberSuspended():
                return Refused("member-suspended")
            case LoanLimitReached():
                return Refused("loan-limit-reached")
            case _:
                assert_never(result)

    def give_back(self, copy: int) -> DeskResponse:
        """A member brings a copy back."""
        result = self._give_back.execute(ReturnCopyCommand(CopyId(copy)))
        match result:
            case Returned(copy=returned):
                return Done(returned.value)
            case UnknownCopy():
                return Refused("unknown-copy")
            case CopyNotOnLoan():
                return Refused("not-on-loan")
            case _:
                assert_never(result)

    def reserve(self, member: int, copy: int) -> DeskResponse:
        """A member reserves a copy."""
        result = self._reserve.execute(ReserveCopyCommand(MemberId(member), CopyId(copy)))
        match result:
            case Reserved(reservation=reservation):
                return Done(reservation.value)
            case UnknownCopy():
                return Refused("unknown-copy")
            case _:
                assert_never(result)
