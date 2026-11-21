"""The models of both contexts, without a store: what each aggregate decides and records."""

from __future__ import annotations

import datetime
import uuid

import pytest
from dca_building_blocks import EventId, Timestamp

from library.catalogue.domain.failure import BlankTitleName, CopyHeldAlready
from library.catalogue.domain.title import CopyAcquired, ShelfMark, ShelfMarks, Title, TitleName, TitleRegistered
from library.catalogue.domain.title_factory import TitleFactory
from library.lending.domain.copy import CopyLent, LendableCopy, OnShelfSpecification
from library.lending.domain.failure import NotOnLoan, NotOnShelf, ReservationClosed
from library.lending.domain.loan import LoanId, LoanPeriod
from library.lending.domain.member import MemberId, MemberStandings, Standing
from library.lending.domain.reservation import Reservation, ReservationId
from library.lending.domain.terms import LoanTerms
from library.sharedkernel.domain.identity import CopyId, TitleId

START = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def at(days: int) -> Timestamp:
    return Timestamp(START + datetime.timedelta(days=days))


def event(number: int) -> EventId:
    return EventId(uuid.UUID(int=number))


class Numbered(ShelfMarks):
    def mark_for(self, name: TitleName, copy: CopyId, /) -> ShelfMark:
        return ShelfMark(f"{name.value}-{copy.value}")


class Standings(MemberStandings):
    def standing_of(self, member: MemberId, /) -> Standing:
        return Standing.SUSPENDED if member == MemberId(9) else Standing.GOOD


def registered() -> Title:
    return TitleFactory().register(TitleId(1), TitleName(" Dune "), event(1), at(0))


def shelved() -> LendableCopy:
    copy = LendableCopy.shelve(CopyId(1), TitleId(2), event(1), at(0))
    copy.clear_domain_events()
    return copy


def test_a_registered_title_records_its_registration() -> None:
    title = registered()
    assert title.name == TitleName("Dune")
    assert [type(e) for e in title.domain_events()] == [TitleRegistered]


def test_an_acquired_copy_is_shelved_under_its_mark_once() -> None:
    title = registered()
    assert title.acquire_copy(Numbered(), CopyId(7), event(2), at(1)) == ShelfMark("Dune-7")
    assert len(title.holdings()) == 1
    assert isinstance(title.domain_events()[-1], CopyAcquired)
    with pytest.raises(CopyHeldAlready):
        title.acquire_copy(Numbered(), CopyId(7), event(3), at(2))


def test_a_blank_name_is_refused() -> None:
    with pytest.raises(BlankTitleName):
        TitleName("  ")


def test_a_copy_on_the_shelf_is_lent_and_due_after_the_period() -> None:
    copy = shelved()
    due = copy.lend(LoanId(3), MemberId(4), None, LoanPeriod(1), event(2), at(0))
    assert due == at(1)
    assert not OnShelfSpecification().is_satisfied_by(copy)
    assert [type(e) for e in copy.domain_events()] == [CopyLent]
    with pytest.raises(NotOnShelf):
        copy.lend(LoanId(5), MemberId(6), None, LoanPeriod(1), event(3), at(1))


def test_a_returned_loan_leaves_the_copy_on_the_shelf() -> None:
    copy = shelved()
    with pytest.raises(NotOnLoan):
        copy.take_back(event(2), at(1))
    copy.lend(LoanId(3), MemberId(4), None, LoanPeriod(1), event(3), at(0))
    copy.take_back(event(4), at(5))
    assert OnShelfSpecification().is_satisfied_by(copy)
    assert [loan.returned_on for loan in copy.loans()] == [at(5)]


def test_the_terms_shorten_a_popular_copy_and_refuse_a_suspended_member() -> None:
    terms = LoanTerms(LoanPeriod(21), Standings())
    copy = shelved()
    assert terms.period_for(copy, MemberId(4)) == LoanPeriod(21)
    assert terms.period_for(copy, MemberId(9)) is None
    for number in range(3):
        copy.lend(LoanId(number), MemberId(4), None, LoanPeriod(1), event(10 + number), at(number))
        copy.take_back(event(20 + number), at(number))
    assert terms.period_for(copy, MemberId(4)) == LoanPeriod(10)


def test_a_reservation_is_fulfilled_once() -> None:
    reservation = Reservation.place(ReservationId(1), MemberId(4), CopyId(1), event(1), at(0))
    reservation.fulfil(event(2), at(1))
    assert reservation.is_fulfilled()
    with pytest.raises(ReservationClosed):
        reservation.fulfil(event(3), at(2))
