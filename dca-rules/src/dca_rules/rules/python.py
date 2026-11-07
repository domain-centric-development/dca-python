"""Python-only rules, `DCA-PY-nnn`: what the language lets slip that the other languages' compilers or the shared
rules hold. All start experimental."""

from __future__ import annotations

import ast

from dca_rules.model import Klass, Project, dotted_name, parameters
from dca_rules.rules import Finding, rule
from dca_rules.rules.errors import closed_results

CLOCK_AND_CHANCE = {
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "datetime.datetime.today",
    "datetime.date.today",
    "time.time",
    "time.time_ns",
    "time.monotonic",
    "time.perf_counter",
    "uuid.uuid1",
    "uuid.uuid4",
    "uuid.uuid7",
    "os.urandom",
    "secrets.token_hex",
    "secrets.token_bytes",
    "secrets.token_urlsafe",
    "secrets.choice",
}


@rule("DCA-PY-001")
def py_001(p: Project) -> list[Finding]:
    """A domain dataclass is frozen, by its base where it is a value, an id or an event."""
    found = []
    for klass in p.classes_in("domain"):
        decorator = p.is_dataclass(klass)
        if decorator is None:
            continue
        if p.roles(klass) & {"Value", "DomainEvent", "IntegrationEvent"}:
            found.append(
                Finding(
                    klass.module.where(decorator),
                    f"{klass.name} is a frozen dataclass by its base; it carries no decorator of its own",
                )
            )
        elif not p.has(klass, "Entity") and not p.is_frozen_dataclass(klass):
            found.append(
                Finding(
                    klass.module.where(decorator),
                    f"{klass.name} is a mutable dataclass in the domain; make it a Value or an Entity",
                )
            )
    return found


@rule("DCA-PY-002")
def py_002(p: Project) -> list[Finding]:
    """An entity compares by identity: neither a dataclass that compares its fields nor an `__eq__` of its own."""
    found = []
    for klass in p.with_role("Entity"):
        decorator = p.is_dataclass(klass)
        if decorator is not None and not (
            isinstance(decorator, ast.Call)
            and any(
                k.arg == "eq" and isinstance(k.value, ast.Constant) and k.value.value is False
                for k in decorator.keywords
            )
        ):
            found.append(
                Finding(
                    klass.module.where(decorator),
                    f"{klass.name} is a dataclass that compares its fields; an entity is equal by its id (eq=False)",
                )
            )
        if "__eq__" in klass.methods:
            found.append(
                Finding(
                    klass.module.where(klass.methods["__eq__"]),
                    f"{klass.name} replaces the identity equality of Entity",
                )
            )
    return found


def _signature(method: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    return tuple(a.arg for a in parameters(method))


def _port_methods(p: Project, port: Klass) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for base in reversed(p.base_classes(port)):
        if base.is_protocol:
            out.update(_port_methods(p, base))
    out.update({n: _signature(m) for n, m in port.methods.items() if not n.startswith("_")})
    return out


@rule("DCA-PY-003")
def py_003(p: Project) -> list[Finding]:
    """An output port is implemented by name: an adapter that fits its shape names it among its bases, and a port
    has at least one class that does. An adapter that names an output port already is held to that one; another
    port it happens to fit is a coincidence of shape, not a second implementation."""
    found = []
    ports = [k for k in p.with_role("OutputPort") if k.is_protocol]
    concrete = [k for k in p.classes.values() if not k.is_protocol]
    named = {k.qualname for k in concrete if any(port.qualname in p.ancestors(k) for port in ports)}
    for port in ports:
        wanted = _port_methods(p, port)
        nominal = [k for k in concrete if port.qualname in p.ancestors(k)]
        if not nominal and not any(port.qualname in p.ancestors(k) for k in ports if k is not port):
            found.append(Finding(port.where(), f"no class names the output port {port.name} among its bases"))
        if not wanted:
            continue
        for klass in concrete:
            if klass.qualname in named or klass.place.layer not in ("outgoing", "root"):
                continue
            own = {n: _signature(m) for n, m in klass.methods.items()}
            if all(own.get(n) == s for n, s in wanted.items()):
                found.append(
                    Finding(
                        klass.where(),
                        f"{klass.name} fits the output port {port.name} by its shape "
                        "and does not name it among its bases",
                    )
                )
    for klass in concrete:
        if klass.place.layer not in ("outgoing", "root"):
            continue
        roles = p.roles(klass)
        for block, methods in BB_PORTS.items():
            if methods <= set(klass.methods) and not roles & BB_PORT_FAMILY[block]:
                found.append(
                    Finding(
                        klass.where(),
                        f"{klass.name} fits the building block {block} by its shape "
                        "and does not name it among its bases",
                    )
                )
    return found


#: The building blocks' own ports by the methods an implementation must define, and the roles that already name
#: one of the same shape (two publishers share `publish`).
BB_PORTS = {
    "Repository": {"find_by_id", "save", "delete_by_id"},
    "DomainEventPublisher": {"publish"},
    "TransactionBoundary": {"in_transaction"},
}
BB_PORT_FAMILY = {
    "Repository": {"Repository"},
    "DomainEventPublisher": {"DomainEventPublisher", "IntegrationEventPublisher"},
    "TransactionBoundary": {"TransactionBoundary"},
}


@rule("DCA-PY-004")
def py_004(p: Project) -> list[Finding]:
    """The domain stays synchronous."""
    found = []
    for module in p.in_layer("domain"):
        for node in ast.walk(module.tree):
            if isinstance(node, ast.AsyncFunctionDef):
                found.append(
                    Finding(
                        module.where(node), f"{module.dotted}.{node.name} is a coroutine; async is the ports' concern"
                    )
                )
            if isinstance(node, ast.Import | ast.ImportFrom):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(n.split(".")[0] in ("asyncio", "trio", "anyio") for n in names):
                    found.append(Finding(module.where(node), f"{module.dotted} imports an async runtime"))
    return found


@rule("DCA-PY-005")
def py_005(p: Project) -> list[Finding]:
    """The domain reads no clock and no randomness."""
    found = []
    for module in p.in_layer("domain"):
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call):
                continue
            name = p.resolve(module, node.func) or ""
            if name in CLOCK_AND_CHANCE or name.startswith("random."):
                found.append(
                    Finding(module.where(node), f"{module.dotted} calls {name}; the value comes in as a parameter")
                )
    return found


def _is_assert_never(body: list[ast.stmt]) -> bool:
    for stmt in body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            name = dotted_name(stmt.value.func) or ""
            if name.endswith("assert_never"):
                return True
        if isinstance(stmt, ast.Raise):
            return False
    return False


@rule("DCA-PY-006")
def py_006(p: Project) -> list[Finding]:
    """A match over a closed result does not swallow a case it does not know: its wildcard is `assert_never`."""
    cases = {c.qualname for _, (_, cs) in closed_results(p).items() for c in cs}
    found = []
    for module in p.modules.values():
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Match):
                continue
            named = set()
            for case in node.cases:
                for item in ast.walk(case.pattern):
                    if isinstance(item, ast.MatchClass):
                        klass = p.klass(module, item.cls)
                        if klass is not None:
                            named.add(klass.qualname)
            if not named & cases:
                continue
            for case in node.cases:
                wildcard = isinstance(case.pattern, ast.MatchAs) and case.pattern.pattern is None
                if wildcard and not _is_assert_never(case.body):
                    found.append(
                        Finding(
                            module.where(case.pattern),
                            f"{module.dotted} matches a closed result and "
                            "swallows every other case; end with case _: assert_never(...)",
                        )
                    )
    return found


CANCELLED = ("BaseException", "asyncio.CancelledError", "CancelledError", "asyncio.exceptions.CancelledError")


@rule("DCA-PY-007")
def py_007(p: Project) -> list[Finding]:
    """Cancellation passes through: a handler that catches it raises again."""
    found = []
    for module in p.modules.values():
        if module.place.layer is None:
            continue
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            caught = (
                [] if node.type is None else (list(node.type.elts) if isinstance(node.type, ast.Tuple) else [node.type])
            )
            names = [p.resolve(module, c) or "" for c in caught]
            catches = node.type is None or any(n.removeprefix("builtins.") in CANCELLED for n in names)
            if catches and not any(isinstance(n, ast.Raise) for n in ast.walk(node)):
                found.append(
                    Finding(module.where(node), f"{module.dotted} catches cancellation and does not raise it again")
                )
    return found
