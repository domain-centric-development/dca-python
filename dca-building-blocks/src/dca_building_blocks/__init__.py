"""Building blocks of Domain-Centric Architecture for Python.

Each class names a role. A class takes the role by naming the building block among its bases; the rule suite
(`dca-rules`) reads the roles from the source. Standard library only, so a domain package can import it and
nothing else.
"""

from dca_building_blocks.application import (
    InputPortException,
    OutputPortException,
    PortException,
    Refusal,
    TransactionBoundary,
    UseCaseException,
)
from dca_building_blocks.ports import (
    AsyncUseCase,
    DomainEventPublisher,
    InputPort,
    IntegrationEventPublisher,
    OutputPort,
    Repository,
    Store,
    UseCase,
)
from dca_building_blocks.strategic import (
    BoundedContext,
    Consumes,
    ExternalUpstream,
    Interaction,
    OpenHostService,
    Partnership,
    SharedKernel,
    Status,
    Translation,
    Upstream,
)
from dca_building_blocks.tactical import (
    AggregateRoot,
    DomainEvent,
    DomainException,
    DomainGateway,
    DomainService,
    Entity,
    EventId,
    Factory,
    Id,
    IntegrationEvent,
    Owned,
    Specification,
    Timestamp,
    Value,
)

__all__ = [
    "AggregateRoot",
    "AsyncUseCase",
    "BoundedContext",
    "Consumes",
    "DomainEvent",
    "DomainEventPublisher",
    "DomainException",
    "DomainGateway",
    "DomainService",
    "Entity",
    "EventId",
    "ExternalUpstream",
    "Factory",
    "Id",
    "InputPort",
    "InputPortException",
    "IntegrationEvent",
    "IntegrationEventPublisher",
    "Interaction",
    "OpenHostService",
    "OutputPort",
    "OutputPortException",
    "Owned",
    "Partnership",
    "PortException",
    "Refusal",
    "Repository",
    "SharedKernel",
    "Specification",
    "Status",
    "Store",
    "Timestamp",
    "TransactionBoundary",
    "Translation",
    "Upstream",
    "UseCase",
    "UseCaseException",
    "Value",
]
