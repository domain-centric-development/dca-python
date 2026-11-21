"""What more than one use case of lending works with. Lending answers its refusals as cases of closed results."""

from __future__ import annotations

import dataclasses
from typing import Protocol

from dca_building_blocks import Refusal, Repository, Store, Timestamp

from library.lending.domain.copy import LendableCopy
from library.lending.domain.loan import LoanId
from library.lending.domain.member import MemberId
from library.lending.domain.reservation import Reservation, ReservationId
from library.sharedkernel.domain.identity import CopyId


class LendableCopyRepository(Repository[LendableCopy, CopyId], Protocol):
    """The copies lending knows."""


class ReservationRepository(Repository[Reservation, ReservationId], Protocol):
    """The reservations: each belongs to its member and is looked up through them."""

    def find_by_id_for_member(self, reservation: ReservationId, member: MemberId, /) -> Reservation | None:
        """The member's reservation with this id; another member's is not found."""
        ...


@dataclasses.dataclass(frozen=True)
class LoanRecord:
    """One loan as the ledger records it."""

    loan: LoanId
    copy: CopyId
    member: MemberId
    lent_on: Timestamp


class LoanLedgerStore(Store, Protocol):
    """The ledger of every loan made: appended to, never changed."""

    def append(self, record: LoanRecord, /) -> None:
        """Records a loan."""
        ...

    def loans_recorded_for(self, member: MemberId, /) -> int:
        """How many loans the ledger records for the member."""
        ...


@dataclasses.dataclass(frozen=True)
class UnknownCopy(Refusal):
    """Refused: lending knows no such copy."""

    copy: CopyId
