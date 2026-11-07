"""Strategic declarations: a bounded context, the shared kernel and the relationships between contexts.

Python has no package annotation, so a context declares itself in its package's `__init__.py` with a module-level
`__dca__`:

    # orders/__init__.py
    from dca_building_blocks.strategic import BoundedContext, Consumes, Translation, Upstream

    __dca__ = BoundedContext(
        name="orders",
        upstreams=(Upstream(context="catalog", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.API,)),),
    )

The rule suite reads the declaration from the source without importing it, so its arguments are literals and the
enums below.
"""

from __future__ import annotations

import dataclasses
import enum


class Translation(enum.Enum):
    """How a downstream context takes over an upstream's model."""

    ANTI_CORRUPTION_LAYER = "acl"
    CONFORMIST = "conformist"


class Consumes(enum.Enum):
    """The channel through which a downstream context uses an upstream: its `api` or its `api.events`."""

    API = "api"
    EVENTS = "events"


class Status(enum.Enum):
    """Whether a declared relationship is in the code already or planned."""

    IMPLEMENTED = "implemented"
    PLANNED = "planned"


class Interaction(enum.Enum):
    """Who calls whom across the boundary to an external system."""

    OUTBOUND = "outbound"
    INBOUND = "inbound"


@dataclasses.dataclass(frozen=True)
class Upstream:
    """Another bounded context of this system that this context depends on."""

    context: str
    translation: Translation
    via: tuple[Consumes, ...]
    rationale: str = ""
    status: Status = Status.IMPLEMENTED


@dataclasses.dataclass(frozen=True)
class ExternalUpstream:
    """A system outside this code base that this context depends on; `contract_packages` name the modules that hold
    its contract types (a generated client, a schema package)."""

    name: str
    translation: Translation
    interaction: Interaction
    contract_packages: tuple[str, ...] = ()
    protocol: str = ""
    exchanges: str = ""
    rationale: str = ""
    status: Status = Status.IMPLEMENTED


@dataclasses.dataclass(frozen=True)
class Partnership:
    """Another context this one evolves together with; the other declares the partnership back."""

    context: str
    rationale: str = ""


@dataclasses.dataclass(frozen=True)
class BoundedContext:
    """The declaration of a bounded context, as `__dca__` in its package's `__init__.py`."""

    name: str
    description: str = ""
    upstreams: tuple[Upstream, ...] = ()
    external_upstreams: tuple[ExternalUpstream, ...] = ()
    partnerships: tuple[Partnership, ...] = ()


@dataclasses.dataclass(frozen=True)
class SharedKernel:
    """The declaration of the shared kernel, as `__dca__` in its package's `__init__.py`."""

    description: str = ""


class OpenHostService:
    """Marks a published interface another bounded context may call: it sits in the context's `api` package or in
    an incoming adapter."""

    __slots__ = ()
