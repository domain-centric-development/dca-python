"""The building blocks keep the promises their docstrings make."""

from __future__ import annotations

import dataclasses
import datetime
import uuid
from collections.abc import Callable

import pytest
from dca_building_blocks import (
    AggregateRoot,
    DomainEvent,
    DomainEventPublisher,
    Entity,
    EventId,
    Id,
    IntegrationEvent,
    Refusal,
    Timestamp,
    TransactionBoundary,
    Value,
)

NOW = Timestamp(datetime.datetime(2026, 11, 7, 12, 0, tzinfo=datetime.UTC))


class Label(Value):
    value: str


class ThingId(Id):
    value: str


class PartAdded(DomainEvent):
    event_id: EventId
    occurred_on: Timestamp
    label: Label


class ThingShipped(IntegrationEvent, event_type="alpha.thing-shipped", version=2):
    thing_id: str


class Thing(AggregateRoot[ThingId]):
    def __init__(self, thing_id: ThingId, label: Label) -> None:
        self._id = thing_id
        self.label = label

    @property
    def id(self) -> ThingId:
        return self._id

    def relabel(self, label: Label) -> None:
        self.label = label
        self.register_event(PartAdded(EventId(uuid.uuid4()), NOW, label))


def test_a_value_is_a_frozen_dataclass_by_its_base() -> None:
    label = Label("a")
    assert dataclasses.is_dataclass(label)
    assert label == Label("a")
    assert hash(label) == hash(Label("a"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        label.value = "b"  # type: ignore[misc]


def test_an_id_is_a_value() -> None:
    assert ThingId("x") == ThingId("x")
    assert ThingId("x") != ThingId("y")


def test_a_timestamp_carries_its_time_zone() -> None:
    with pytest.raises(ValueError):
        Timestamp(datetime.datetime(2026, 11, 7))


def test_entities_compare_by_identity() -> None:
    a = Thing(ThingId("1"), Label("a"))
    b = Thing(ThingId("1"), Label("b"))
    assert a == b
    assert a.same_identity_as(b)
    assert a != Thing(ThingId("2"), Label("a"))
    assert len({a, b}) == 1


def test_an_aggregate_records_its_events_until_they_are_cleared() -> None:
    thing = Thing(ThingId("1"), Label("a"))
    thing.relabel(Label("b"))
    assert [type(e) for e in thing.domain_events()] == [PartAdded]
    published: list[DomainEvent] = []

    class Recording(DomainEventPublisher):
        def publish(self, event: DomainEvent, /) -> None:
            published.append(event)

    Recording().publish_and_clear_events(thing)
    assert len(published) == 1
    assert thing.domain_events() == ()


def test_an_integration_event_carries_its_type_on_the_class() -> None:
    assert ThingShipped.EVENT_TYPE == "alpha.thing-shipped"
    assert ThingShipped.EVENT_VERSION == 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        ThingShipped("1").thing_id = "2"  # type: ignore[misc]


def test_an_integration_event_without_its_type_is_refused() -> None:
    with pytest.raises(TypeError, match="event_type"):

        class Untyped(IntegrationEvent):
            payload: str


class Recording(TransactionBoundary):
    def __init__(self) -> None:
        self.log: list[str] = []

    def in_transaction[T](self, work: Callable[[], T], /) -> T:
        try:
            result = work()
        except BaseException:
            self.log.append("rollback")
            raise
        self.log.append("commit")
        return result


@dataclasses.dataclass(frozen=True)
class Done:
    pass


@dataclasses.dataclass(frozen=True)
class Taken(Refusal):
    seat: int


def test_a_returned_refusal_rolls_back_and_comes_back_as_the_answer() -> None:
    boundary = Recording()
    answer: Done | Taken = boundary.in_transaction_closed(lambda: Taken(3))
    assert answer == Taken(3)
    assert boundary.log == ["rollback"]


def test_a_success_commits() -> None:
    boundary = Recording()
    assert boundary.in_transaction_closed(Done) == Done()
    assert boundary.log == ["commit"]


def test_a_failure_still_rolls_back() -> None:
    boundary = Recording()

    def broken() -> Done:
        raise RuntimeError("broken")

    with pytest.raises(RuntimeError):
        boundary.in_transaction_closed(broken)
    assert boundary.log == ["rollback"]


def test_entity_is_abstract() -> None:
    with pytest.raises(TypeError):
        Entity()  # type: ignore[abstract]
