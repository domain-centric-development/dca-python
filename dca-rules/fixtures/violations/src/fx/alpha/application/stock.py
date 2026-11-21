"""Use cases that hide what they do behind aliases, helpers, bases and generic arguments."""

import abc
import dataclasses
import typing
import uuid

from dca_building_blocks import DomainEventPublisher, Refusal, UseCase
from fx.alpha.application.shared import ThingRepository
from fx.alpha.application.things.remove_part import RemovePartInputPort
from fx.alpha.domain.model import Thing, ThingFull, ThingId


@dataclasses.dataclass(frozen=True)
class StockCommand:
    key: ThingId


@dataclasses.dataclass(frozen=True)
class StockTallyQuery:
    key: ThingId


@dataclasses.dataclass(frozen=True)
class StockResult:
    key: ThingId


@dataclasses.dataclass(frozen=True)
class StockRefused(Refusal):
    key: ThingId


class StockInputPort(UseCase[StockCommand, StockResult], typing.Protocol):
    pass


class StockTallyInputPort(UseCase[StockTallyQuery, StockResult], typing.Protocol):
    pass


class RestockAfterSaleInputPort(UseCase[StockCommand, StockResult], typing.Protocol):  # DCA-NAM-012
    pass


class Remembering:
    """A base without a role: its methods are the use case's own."""

    def remember(self, key: ThingId) -> None:
        self._last = key  # DCA-USE-021: state kept through a role-less base


class StockUseCase(Remembering, StockInputPort):
    def __init__(
        self,
        things: ThingRepository,
        events: DomainEventPublisher,
        router: RemovePartInputPort,  # DCA-USE-016: a parameter is a dependency as well
    ) -> None:
        self._things = things
        self._events = events

    def execute(self, command: StockCommand, /) -> StockResult:  # DCA-USE-009: saves through a helper
        thing = self._things.find_by_id(command.key)
        self._keep(thing)
        return StockResult(command.key)

    def _keep(self, thing: Thing) -> None:
        things = self._things
        things.save(thing)  # DCA-USE-012: an alias of the repository, outside the boundary

    def _announce(self, thing: Thing) -> None:
        self._events.publish_and_clear_events(thing)


class StockTallyUseCase(StockTallyInputPort):
    def __init__(self, things: ThingRepository, events: DomainEventPublisher) -> None:
        self._things = things
        self._events = events

    def execute(self, query, /):  # noqa: ANN001, ANN201 - the query is read from UseCase[Q, R]
        self._things.save_all([])  # DCA-USE-019: a write by its verb
        self._events.publish_later(query)  # DCA-USE-019: any publisher call
        if query is None:
            raise ThingFull  # DCA-ERR-009: raising the class constructs it
        return StockResult(query.key)


class Gone(KeyError):  # DCA-ERR-003: a built-in exception subclass in the application
    pass


def parse_key(raw: str) -> ThingId:
    return ThingId(uuid.UUID(raw))  # DCA-USE-020: anywhere in the application


class StockCaller:
    def __init__(self, port: StockInputPort) -> None:
        self._port = port

    def call(self, command: StockCommand) -> None:
        port = self._port
        try:
            port.execute(command)
        except Exception:  # DCA-ERR-010: an alias of the port field
            pass

    def call_and_undo(self, command: StockCommand) -> None:
        try:
            self._port.execute(command)
        except BaseException:  # cleans up and hands the failure on unchanged: no finding
            self.undone = True
            raise

    def call_and_wrap(self, command: StockCommand) -> None:
        try:
            self._port.execute(command)
        except Exception as failure:  # DCA-ERR-010: handed on wrapped, not unchanged
            raise RuntimeError("stock") from failure

    def call_or_return(self, command: StockCommand) -> None:
        try:
            self._port.execute(command)
        except Exception:  # DCA-ERR-010: a return leaves the handler another way
            if self.undone:
                return
            raise


class ShelveInputPort(UseCase[StockCommand, StockResult], abc.ABC):
    """An abstract base class with abstract methods only: an input port, no use case (DCA-NAM-001 stays silent)."""

    @abc.abstractmethod
    def execute(self, command: StockCommand, /) -> StockResult: ...
