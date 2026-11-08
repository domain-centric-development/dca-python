"""Python-only rules, `DCA-PY-nnn`: what the language lets slip that the other languages' compilers or the shared
rules hold. All start experimental."""

from __future__ import annotations

import ast

from dca_rules.model import Klass, Project, dotted_name, parameters
from dca_rules.rules import Checked, Finding, rule
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
def py_001(p: Project) -> Checked:
    """A domain dataclass is frozen, by its base where it is a value, an id or an event."""
    found = []
    selected = [(k, d) for k in p.classes_in("domain") if (d := p.is_dataclass(k)) is not None]
    for klass, decorator in selected:
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
    return Checked(len(selected), found)


@rule("DCA-PY-002")
def py_002(p: Project) -> Checked:
    """An entity compares by identity: neither a dataclass that compares its fields nor an `__eq__` of its own."""
    found = []
    selected = p.with_role("Entity")
    for klass in selected:
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
    return Checked(len(selected), found)


def _signature(method: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    return tuple(a.arg for a in parameters(method))


def _port_methods(p: Project, port: Klass) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for base in reversed(p.base_classes(port)):
        if base.is_protocol:
            out.update(_port_methods(p, base))
    out.update({n: _signature(m) for n, m in port.methods.items() if not n.startswith("_")})
    return out


#: The ports the building blocks declare, each with the words a finding names it by: what the application needs from
#: outside, and what the domain asks of the outside to obtain a fact it does not hold.
PORT_KINDS = {"OutputPort": "output port", "DomainGateway": "domain gateway"}


@rule("DCA-PY-003")
def py_003(p: Project) -> Checked:
    """A port is implemented by name - an output port or a domain gateway: an adapter that fits its shape names it
    among its bases, and a port has at least one class that does. An adapter that names a port already is held to
    that one; another port it happens to fit is a coincidence of shape, not a second implementation."""
    found = []
    ports = [(k, kind) for role, kind in PORT_KINDS.items() for k in p.with_role(role) if k.is_protocol]
    protocols = [k for k, _ in ports]
    concrete = [k for k in p.classes.values() if not k.is_protocol]
    adapters = [k for k in concrete if k.place.layer in ("outgoing", "root")]
    named = {k.qualname for k in concrete if any(port.qualname in p.ancestors(k) for port in protocols)}
    for port, kind in ports:
        wanted = _port_methods(p, port)
        nominal = [k for k in concrete if port.qualname in p.ancestors(k)]
        if not nominal and not any(port.qualname in p.ancestors(k) for k in protocols if k is not port):
            found.append(Finding(port.where(), f"no class names the {kind} {port.name} among its bases"))
        if not wanted:
            continue
        for klass in adapters:
            if klass.qualname in named:
                continue
            own = {n: _signature(m) for n, m in klass.methods.items()}
            if all(own.get(n) == s for n, s in wanted.items()):
                found.append(
                    Finding(
                        klass.where(),
                        f"{klass.name} fits the {kind} {port.name} by its shape and does not name it among its bases",
                    )
                )
    for klass in adapters:
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
    return Checked(len({k.qualname for k in protocols + adapters}), found)


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
def py_004(p: Project) -> Checked:
    """The domain stays synchronous."""
    found = []
    selected = p.in_layer("domain")
    for module in selected:
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
    return Checked(len(selected), found)


@rule("DCA-PY-005")
def py_005(p: Project) -> Checked:
    """The domain reads no clock and no randomness."""
    found = []
    selected = p.in_layer("domain")
    for module in selected:
        for node in ast.walk(module.tree):
            if not isinstance(node, ast.Call):
                continue
            name = p.resolve(module, node.func) or ""
            if name in CLOCK_AND_CHANCE or name.startswith("random."):
                found.append(
                    Finding(module.where(node), f"{module.dotted} calls {name}; the value comes in as a parameter")
                )
    return Checked(len(selected), found)


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
def py_006(p: Project) -> Checked:
    """A match over a closed result does not swallow a case it does not know: its wildcard is `assert_never`.
    Selects the matches that name a case of a closed result."""
    cases = {c.qualname for _, (_, cs) in closed_results(p).items() for c in cs}
    found = []
    selected = 0
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
            selected += 1
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
    return Checked(selected, found)


CANCELLED = ("BaseException", "asyncio.CancelledError", "CancelledError", "asyncio.exceptions.CancelledError")


@rule("DCA-PY-007")
def py_007(p: Project) -> Checked:
    """Cancellation passes through: a handler that catches it raises again."""
    found = []
    selected = [m for m in p.modules.values() if m.place.layer is not None]
    for module in selected:
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
    return Checked(len(selected), found)


@rule("DCA-PY-008")
def py_008(p: Project) -> Checked:
    """A use case is implemented by name: a class of the application that executes names an input port among its
    bases, and every input port has a class that names it."""
    found = []
    ports = [k for k in p.with_role("InputPort") if k.is_protocol]
    concrete = [k for k in p.classes.values() if not k.is_protocol]
    executing = [k for k in concrete if k.place.layer == "application" and "execute" in k.methods]
    for port in ports:
        named = any(port.qualname in p.ancestors(k) for k in concrete)
        narrowed = any(port.qualname in p.ancestors(k) for k in ports if k is not port)
        if not named and not narrowed:
            found.append(Finding(port.where(), f"no class names the input port {port.name} among its bases"))
    for klass in executing:
        if "InputPort" not in p.roles(klass):
            found.append(
                Finding(klass.where(), f"{klass.name} executes a use case and names no input port among its bases")
            )
    return Checked(len(ports) + len(executing), found)
