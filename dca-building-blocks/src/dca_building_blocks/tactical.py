"""Tactical building blocks: values, identities, entities, aggregates, events, services, failures.

A class takes a role by naming the building block among its bases; the rule suite reads the roles from the source,
so a role is always nominal, never structural. `Value`, `Id`, `DomainEvent` and `IntegrationEvent` make every
subclass a frozen dataclass by their base: the subclass declares its fields and carries no decorator of its own.
"""

from __future__ import annotations

import abc
import dataclasses
import datetime
import typing
import uuid


def _frozen(cls: type, home: str) -> None:
    """Make a subclass of a marker a frozen dataclass; the markers declared in this package stay plain classes."""
    if not cls.__module__.startswith(home):
        dataclasses.dataclass(frozen=True)(cls)


_HOME = __name__.rsplit(".", 1)[0]


@typing.dataclass_transform(frozen_default=True)
class Value:
    """A value object: described by its attributes, without identity, never changed after it is built.

    Every subclass is a frozen dataclass by this base: two values with equal attributes are equal, an assignment
    to a field raises, a change produces a new instance. It validates itself in `__post_init__` and references no
    aggregate root and no entity.

        class Label(Value):
            value: str

            def __post_init__(self) -> None:
                if not self.value.strip():
                    raise ValueError("a label is not blank")
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: typing.Any) -> None:
        super().__init_subclass__(**kwargs)
        _frozen(cls, _HOME)


class Id(Value):
    """A typed identity. An entity is identified by one, never by a bare string or number: one type per entity
    lets the type checker refuse one aggregate's id where another's is expected."""

    __slots__ = ()


@dataclasses.dataclass(frozen=True)  # declared here, so its base leaves it to this decorator
class EventId(Id):
    """The identity of an event: a UUID, wrapped so a domain field never holds a bare one."""

    value: uuid.UUID


@dataclasses.dataclass(frozen=True)  # declared here, so its base leaves it to this decorator
class Timestamp(Value):
    """A point in time, timezone-aware. The domain receives it as a value; it never reads a clock itself."""

    value: datetime.datetime

    def __post_init__(self) -> None:
        if self.value.tzinfo is None:
            raise ValueError("a timestamp carries its time zone")


class Entity[ID: Id](abc.ABC):
    """An object with an identity that stays the same while its state changes.

    Two entities are equal when they are the same entity: same type, same id, whatever their state. A subclass is
    not a dataclass that compares its fields; it changes state through behaviour named in the ubiquitous language,
    never through setters. An entity that is not an aggregate root lives inside one aggregate and is reached from
    its root only.
    """

    @property
    @abc.abstractmethod
    def id(self) -> ID:
        """The identity, stable for the entity's life."""

    def same_identity_as(self, other: Entity[ID] | None) -> bool:
        """Whether `other` is the same entity, whatever state either is in; False for None."""
        return other is not None and type(other) is type(self) and self.id == other.id

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Entity) and self.same_identity_as(other)

    def __hash__(self) -> int:
        return hash((type(self), self.id))


@typing.dataclass_transform(frozen_default=True)
class DomainEvent:
    """Something that happened in the domain, named in the past tense, recorded by an aggregate.

    A frozen dataclass by this base. It carries its identity (`event_id: EventId`), the moment it happened
    (`occurred_on: Timestamp`) and the event's data; it is internal to its bounded context and evolves without a
    schema version.
    """

    __slots__ = ()

    def __init_subclass__(cls, **kwargs: typing.Any) -> None:
        super().__init_subclass__(**kwargs)
        _frozen(cls, _HOME)


@typing.dataclass_transform(frozen_default=True)
class IntegrationEvent:
    """A published fact another bounded context may consume. Its type and schema version are part of the contract
    and live on the class, not in the payload:

        class ThingShipped(IntegrationEvent, event_type="alpha.thing-shipped", version=1):
            event_id: uuid.UUID
            occurred_on: datetime.datetime
            thing_id: str

    A frozen dataclass by this base; a subclass without `event_type` is refused when the class is created.
    """

    __slots__ = ()
    EVENT_TYPE: typing.ClassVar[str]
    EVENT_VERSION: typing.ClassVar[int]

    def __init_subclass__(cls, *, event_type: str | None = None, version: int = 1, **kwargs: typing.Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__module__.startswith(_HOME):
            return
        if not event_type:
            raise TypeError(
                f"{cls.__name__} names its event_type: class {cls.__name__}(IntegrationEvent, "
                f"event_type=..., version=...)"
            )
        if version < 1:
            raise TypeError(f"{cls.__name__}: an integration event's version starts at 1")
        cls.EVENT_TYPE = event_type
        cls.EVENT_VERSION = version
        _frozen(cls, _HOME)


class AggregateRoot[ID: Id](Entity[ID]):
    """The root of an aggregate: the only entry for changes, the keeper of its invariants and the collector of
    what happened. Another aggregate is referenced by its id; no repository, no output port is held.

        thing.add_part(part, now)             # 1. the root changes state and records its event
        things.save(thing)                    # 2. the repository saves the aggregate
        events.publish_and_clear_events(thing)  # 3. the use case publishes and clears the events

    The root is built through its own class methods (`create`, `restore`), which check its invariants; outside
    the module that declares it, nobody calls the class itself.
    """

    def _pending(self) -> list[DomainEvent]:
        pending: list[DomainEvent] | None = self.__dict__.get("_dca_domain_events")
        if pending is None:
            pending = []
            self.__dict__["_dca_domain_events"] = pending
        return pending

    def register_event(self, event: DomainEvent) -> None:
        """Record an event, from the aggregate's own behaviour, to be published after the aggregate is saved."""
        if not isinstance(event, DomainEvent):
            raise TypeError(f"{event!r} is no domain event")
        self._pending().append(event)

    def domain_events(self) -> tuple[DomainEvent, ...]:
        """The events recorded since they were last cleared, in order."""
        return tuple(self._pending())

    def clear_domain_events(self) -> None:
        """Forget the recorded events once they are published, so none is published twice."""
        self._pending().clear()


class Owned[OWNER: Id]:
    """Marks an aggregate that belongs to someone; the type argument names the owner's id type:

        class Record(AggregateRoot[RecordId], Owned[PatientId]): ...

    Its repository declares a lookup by the aggregate's id and the owner's id, so a use case acting for a caller
    loads it through the caller and an id alone is never the only way in."""

    __slots__ = ()


class DomainService:
    """Domain logic that belongs to no single entity or value and works on aggregates or entities. Stateless: it
    holds its dependencies, set once, and nothing else; the application creates and calls it."""

    __slots__ = ()


class Factory:
    """Builds an aggregate or an entity whose construction is too involved for the type itself. Stateless, named
    `<Type>Factory`, in the domain."""

    __slots__ = ()


class Specification[T](abc.ABC):
    """A predicate over a domain object, named in the ubiquitous language."""

    @abc.abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Whether the candidate satisfies the specification."""


class DomainGateway(typing.Protocol):
    """An interface the domain declares to obtain facts it does not hold, in its own language, implemented by an
    outgoing adapter. It never writes to the outside: it enriches the model so the model can decide."""


class DomainException(Exception):
    """A business rule broken, named in the language of the model. Only the domain raises one; an argument guard
    stays the platform's own (`ValueError`, `TypeError`), and translating it into a protocol's answer is the
    incoming adapter's work."""
