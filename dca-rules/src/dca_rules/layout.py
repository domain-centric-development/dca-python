"""Where the layers are, and what a project tells the suite in `[tool.dca]` of its `pyproject.toml`.

    <source-root>/<base-package>/
        <context>/                  a bounded context; __init__.py declares it: __dca__ = BoundedContext(...)
            domain/                 the model
            application/            use cases, ports; shared/ holds the context's shared output ports
            adapter/incoming/       driving adapters; event/ consumes events, web/ serves pages
            adapter/outgoing/       driven adapters
            infrastructure/         the context's wiring (optional)
            api/                    what the context publishes; events/ its integration events
        sharedkernel/               the shared kernel; __init__.py declares it: __dca__ = SharedKernel()
        infrastructure/             the composition root

Every name is configurable; the defaults are the ones DCA uses in every language.
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


#: Where a framework declares a claims-only check on the route: a decorator (Django, Flask) or a parameter default
#: (FastAPI's Security/Depends). Empty switches DCA-HEX-020 off: without a declarative form there is nothing to advise.
AUTHORIZATION = (
    "django.contrib.auth.decorators.permission_required",
    "django.contrib.auth.decorators.user_passes_test",
    "fastapi.Security",
    "flask_login.login_required",
    "litestar.Router.guards",
)


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
    frameworks: tuple[str, ...] = FRAMEWORKS
    allowed_in_domain: tuple[str, ...] = ()
    timestamp_types: tuple[str, ...] = ("Timestamp", "datetime")
    router_methods: tuple[str, ...] = ROUTER_METHODS
    listener_decorators: tuple[str, ...] = ()
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
