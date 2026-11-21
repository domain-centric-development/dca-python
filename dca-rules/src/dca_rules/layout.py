"""Where the layers are, and what a project tells the suite in `[tool.dca]` of its `pyproject.toml`.

    <source-root>/<base-package>/
        <context>/                  a bounded context; __init__.py declares it: __dca__ = BoundedContext(...)
            domain/                 the model
            application/            use cases, ports; shared/ holds the context's shared output ports
            adapter/incoming/       driving adapters; event/ consumes events, web/ serves pages
            adapter/outgoing/       driven adapters
            infrastructure/         the context's wiring (optional)
            api/                    the operations the context publishes (an open host service)
            events/                 the integration events the context publishes, beside api/
        sharedkernel/               the shared kernel; __init__.py declares it: __dca__ = SharedKernel(). The same
                                    layers as a context (domain/, application/, adapter/, infrastructure/), no
                                    api/ and no events/: shared domain objects, shared ports and their technical
                                    adapters (a shared outbox). Every context may use it layer by layer; it uses no
                                    context.
        infrastructure/             the composition root

Every name is configurable, the package names and the name suffixes alike (Java's `DcaLayout` with…Subpackage and
with…Suffix); the defaults are the ones DCA uses in every language.
"""

from __future__ import annotations

import dataclasses
import pathlib
import tomllib
import typing

#: Frameworks whose decorators and bases are prohibited metadata in the domain, and which the application reaches
#: through its ports only. A preset, extended or replaced per project.
FRAMEWORKS = (
    "django",
    "fastapi",
    "flask",
    "litestar",
    "marshmallow",
    "pydantic",
    "sqlalchemy",
    "sqlmodel",
    "starlette",
)

#: Router presets: a decorator `<anything>.<method>` registers a handler (FastAPI, Flask, Litestar style);
#: `route`/`api_route` with `methods=[...]` too.
ROUTER_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "route", "api_route", "websocket")

#: Class-based view presets (Django, Flask, Litestar, Starlette): a class below one of these handles the HTTP methods
#: it defines.
VIEW_BASES = (
    "django.views",
    "flask.views.View",
    "flask.views.MethodView",
    "litestar.Controller",
    "litestar.controller.Controller",
    "starlette.endpoints.HTTPEndpoint",
)


#: Where a framework declares a claims-only check on the route: a decorator (Django, Flask) or a parameter default
#: (FastAPI's Security/Depends). Empty switches DCA-HEX-020 off: without a declarative form there is nothing to advise.
AUTHORIZATION = (
    "django.contrib.auth.decorators.permission_required",
    "django.contrib.auth.decorators.user_passes_test",
    "fastapi.Security",
    "flask_login.login_required",
    "litestar.Router.guards",
)


#: DCA-ONI-004: the standard library's asynchronous types, by qualified name or prefix. Outside the domain gateways and
#: domain services the domain names none of them.
ASYNC_TYPES = (
    "typing.Awaitable",
    "typing.Coroutine",
    "typing.AsyncIterator",
    "typing.AsyncIterable",
    "typing.AsyncGenerator",
    "collections.abc.Awaitable",
    "collections.abc.Coroutine",
    "collections.abc.AsyncIterator",
    "collections.abc.AsyncIterable",
    "collections.abc.AsyncGenerator",
)

#: DCA-ONI-004: asynchronous runtimes and executors; the domain names none of them anywhere, its gateways included.
ASYNC_RUNTIMES = ("asyncio", "concurrent.futures", "trio", "anyio")

#: DCA-LAY-008: persistence and transaction libraries the application imports none of - it reaches them through its
#: ports and the transaction boundary. A preset, extended or replaced per project.
PERSISTENCE_APIS = (
    "sqlite3",
    "sqlalchemy",
    "sqlmodel",
    "psycopg",
    "psycopg2",
    "asyncpg",
    "pymongo",
    "motor",
    "peewee",
    "tortoise",
    "django.db",
)

#: DCA-LAY-004: decorators that declare a transaction (Django's atomic, a `transactional` of a framework or of the
#: project). A preset, extended or replaced per project.
TRANSACTION_DECORATORS = ("django.db.transaction.atomic", "transactional", "Transactional")

#: DCA-LAY-004: what code runs a transaction with - called or entered by qualified name, or, with a leading dot, a
#: method entered in a `with` on any receiver (SQLAlchemy's `session.begin()`).
TRANSACTION_APIS = ("django.db.transaction.atomic", ".begin", ".begin_nested")


@dataclasses.dataclass(frozen=True)
class DcaLayout:
    """The layout and the switches of one project."""

    project_root: pathlib.Path
    base_package: str
    source_root: str = "src"
    shared_kernel: str = "sharedkernel"
    infrastructure: str = "infrastructure"
    domain: str = "domain"
    application: str = "application"
    shared: str = "shared"
    adapter: str = "adapter"
    incoming: str = "incoming"
    outgoing: str = "outgoing"
    event: str = "event"
    web: str = "web"
    api: str = "api"
    events: str = "events"
    #: Packages of an application layer that only group operations and are no feature or operation themselves
    #: (Java's withOperationContainers): skipped at the front before depth and feature slices are measured.
    operation_containers: tuple[str, ...] = ()
    #: The name suffixes the suite selects by.
    use_case_suffix: str = "UseCase"
    input_port_suffix: str = "InputPort"
    aggregate_root_suffix: str = "AggregateRoot"
    repository_suffix: str = "Repository"
    store_suffix: str = "Store"
    factory_suffix: str = "Factory"
    specification_suffix: str = "Specification"
    frameworks: tuple[str, ...] = FRAMEWORKS
    allowed_in_domain: tuple[str, ...] = ()
    timestamp_types: tuple[str, ...] = ("Timestamp", "datetime")
    #: The class or static method that rebuilds a stored domain object, matched ignoring case: DCA-TAC-025 lets it
    #: take a `bool` - the stored yes/no fact handed back, no flag argument. Empty exempts no factory.
    reconstituting_factories: tuple[str, ...] = ("reconstitute", "restore")
    router_methods: tuple[str, ...] = ROUTER_METHODS
    #: Class-based views: a class extending one of these (by qualified name or below it) handles the HTTP methods it
    #: defines (`get`, `post`, ...).
    view_bases: tuple[str, ...] = VIEW_BASES
    #: DCA-HEX-017: decorators that register a function as an event listener in the publishing transaction (a
    #: framework's in-transaction signal). Empty by default: the building blocks' EventListener is the declaration.
    listener_decorators: tuple[str, ...] = ()
    async_types: tuple[str, ...] = ASYNC_TYPES
    async_runtimes: tuple[str, ...] = ASYNC_RUNTIMES
    persistence_apis: tuple[str, ...] = PERSISTENCE_APIS
    #: DCA-LAY-004: decorators that declare a transaction, matched by qualified name or its last segments.
    transaction_decorators: tuple[str, ...] = TRANSACTION_DECORATORS
    #: DCA-LAY-004: what runs a transaction in code - a qualified name called or entered (`with transaction.atomic():`),
    #: or, starting with a dot, a method entered on any receiver (`with session.begin():`).
    transaction_apis: tuple[str, ...] = TRANSACTION_APIS
    authorization_decorators: tuple[str, ...] = AUTHORIZATION
    #: Further modules that count as `dca_building_blocks`, for a project that keeps its own copy of the markers
    #: (a tool that may not depend on the distribution). They are not read as the project's modules.
    building_blocks: tuple[str, ...] = ()
    experimental: tuple[str, ...] | typing.Literal["all"] = ()
    disabled: tuple[str, ...] = ()
    #: (rule id, reason) for every rule this project lets select nothing: a statement about the project ("no class
    #: is a factory"), written in `[tool.dca]` as `allow-empty = [{ rule = "DCA-ADV-013", reason = "..." }]`.
    allow_empty: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        for rule_id, reason in self.allow_empty:
            if not reason.strip():
                raise ValueError(f"allow-empty names {rule_id} without a reason")
        names = (
            "domain",
            "application",
            "shared",
            "adapter",
            "incoming",
            "outgoing",
            "event",
            "web",
            "api",
            "events",
            "shared_kernel",
            "infrastructure",
        )
        suffixes = tuple(f.name for f in dataclasses.fields(self) if f.name.endswith("_suffix"))
        for field in names + suffixes:
            value = getattr(self, field)
            if not isinstance(value, str) or not value.isidentifier():
                raise ValueError(f"{field.replace('_', '-')} = {value!r} is no identifier")
        if self.incoming == self.outgoing:
            raise ValueError(f"incoming and outgoing are both {self.incoming!r}; the two directions need two names")
        for container in self.operation_containers:
            if not isinstance(container, str) or not container.isidentifier() or container == self.shared:
                raise ValueError(f"operation-containers names {container!r}: an identifier, not the shared package")

    @property
    def package_dir(self) -> pathlib.Path:
        return self.project_root / self.source_root / self.base_package.replace(".", "/")

    def experimental_on(self, rule_id: str) -> bool:
        return self.experimental == "all" or rule_id in self.experimental

    def allowed_empty(self, rule_id: str) -> str | None:
        """The reason this project gives for the rule to select nothing, or None when it gives none."""
        return next((reason for allowed, reason in self.allow_empty if allowed == rule_id), None)

    @classmethod
    def from_pyproject(cls, path: str | pathlib.Path = "pyproject.toml") -> DcaLayout:
        """The layout `[tool.dca]` of this `pyproject.toml` declares; keys are written with dashes."""
        file = pathlib.Path(path).resolve()
        with file.open("rb") as handle:
            table = tomllib.load(handle).get("tool", {}).get("dca", {})
        if "base-package" not in table:
            raise ValueError(f"{file}: [tool.dca] names its base-package")
        values: dict[str, typing.Any] = {}
        for field in dataclasses.fields(cls):
            key = field.name.replace("_", "-")
            if field.name == "project_root" or key not in table:
                continue
            raw = table[key]
            if field.name == "allow_empty":
                values[field.name] = _allow_empty(file, raw)
                continue
            values[field.name] = tuple(raw) if isinstance(raw, list) else raw
        if "extra-frameworks" in table:
            values["frameworks"] = tuple(values.get("frameworks", FRAMEWORKS)) + tuple(table["extra-frameworks"])
        return cls(project_root=file.parent, **values)


def _allow_empty(file: pathlib.Path, raw: object) -> tuple[tuple[str, str], ...]:
    """`allow-empty = [{ rule = "DCA-...", reason = "..." }, ...]`: every entry names its rule and why."""
    if not isinstance(raw, list):
        raise ValueError(f"{file}: allow-empty is a list of {{ rule = ..., reason = ... }}")
    out = []
    for entry in raw:
        rule_id = entry.get("rule") if isinstance(entry, dict) else None
        reason = entry.get("reason") if isinstance(entry, dict) else None
        if not isinstance(rule_id, str) or not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"{file}: allow-empty takes {{ rule = ..., reason = ... }}, a reason given, not {entry!r}")
        out.append((rule_id, reason))
    return tuple(out)
