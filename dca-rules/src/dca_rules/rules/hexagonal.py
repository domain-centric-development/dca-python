"""Hexagonal and strategic rules over what the source names: ports, adapters, handlers, published contracts."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator

from dca_rules.model import Klass, Module, Project, dotted_name
from dca_rules.rules import Finding, rule


def named_classes(p: Project, module: Module) -> Iterator[tuple[ast.expr, Klass]]:
    """Every project class a module names - imported or used -, once per place it names it."""
    for item in module.imports:
        for line_name in item.absolute:
            klass = p.classes.get(p.canonical(line_name))
            if klass is not None:
                yield ast.Constant(value=None, lineno=item.line), klass
    for node, name in p.refs(module, module.tree):
        klass = p.classes.get(name)
        if klass is not None:
            yield node, klass


def _names(p: Project, layer: str, test: str, what: str, predicate: Callable[[Klass], bool]) -> list[Finding]:
    found = []
    for module in p.in_layer(layer):
        seen = set()
        for node, klass in named_classes(p, module):
            if klass.qualname in seen or not predicate(klass):
                continue
            seen.add(klass.qualname)
            found.append(Finding(module.where(node), f"{module.dotted} names {test} {klass.name}: {what}"))
    return found


def is_use_case(p: Project, klass: Klass) -> bool:
    return p.has(klass, "InputPort") and not klass.is_protocol


@rule("DCA-HEX-003")
def hex_003(p: Project) -> list[Finding]:
    return _names(
        p, "incoming", "the repository", "an incoming adapter drives an input port", lambda k: p.has(k, "Repository")
    )


@rule("DCA-HEX-008")
def hex_008(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the class {k.name} sits in {k.module.dotted}, outside the outgoing adapters")
        for k in p.classes.values()
        if k.name.endswith("Repository") and not k.is_protocol and k.place.layer != "outgoing"
    ]


@rule("DCA-HEX-009")
def hex_009(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the protocol {k.name} in application.shared does not extend OutputPort")
        for k in p.classes_in("application")
        if k.place.shared and k.is_protocol and not p.has(k, "OutputPort")
    ]


@rule("DCA-HEX-010")
def hex_010(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the output port {k.name} is declared in the domain")
        for k in p.with_role("OutputPort")
        if k.is_protocol and k.place.layer == "domain"
    ]


@rule("DCA-HEX-011")
def hex_011(p: Project) -> list[Finding]:
    return _names(
        p, "incoming", "the use case", "an incoming adapter depends on the input port", lambda k: is_use_case(p, k)
    )


@rule("DCA-HEX-012")
def hex_012(p: Project) -> list[Finding]:
    return _names(
        p,
        "incoming",
        "the domain service",
        "an incoming adapter drives an input port",
        lambda k: p.has(k, "DomainService"),
    )


@rule("DCA-HEX-013")
def hex_013(p: Project) -> list[Finding]:
    return _names(
        p,
        "outgoing",
        "the input port",
        "an outgoing adapter is driven, it drives nothing",
        lambda k: p.has(k, "InputPort"),
    )


def handlers(p: Project) -> Iterator[tuple[Module, ast.FunctionDef | ast.AsyncFunctionDef, str, ast.Call]]:
    """(module, function, HTTP method, decorator) for every function a router decorator registers: a decorator
    `<router>.<method>("/path", ...)` of the configured router methods."""
    for module in p.modules.values():
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)):
                    continue
                method = decorator.func.attr
                path = decorator.args[0] if decorator.args else None
                if method not in p.layout.router_methods or not (
                    isinstance(path, ast.Constant) and isinstance(path.value, str) and path.value.startswith("/")
                ):
                    continue
                if method in ("route", "api_route"):
                    methods = next((k.value for k in decorator.keywords if k.arg == "methods"), None)
                    names = [e.value for e in getattr(methods, "elts", []) if isinstance(e, ast.Constant)]
                    method = "get" if not names or "GET" in names else str(names[0]).lower()
                yield module, node, method, decorator


@rule("DCA-HEX-014")
def hex_014(p: Project) -> list[Finding]:
    found = []
    for module, function, method, _ in handlers(p):
        if method != "get":
            continue
        for call, klass in p.constructions(module, function):
            if klass.name.endswith("Command"):
                found.append(
                    Finding(
                        module.where(call),
                        f"the GET handler {function.name} drives an input port with the command {klass.name}",
                    )
                )
    return found


@rule("DCA-HEX-016")
def hex_016(p: Project) -> list[Finding]:
    found = []
    for module in p.in_layer("incoming", "outgoing", "adapter"):
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Attribute) and node.attr == "name" and isinstance(node.value, ast.Attribute):
                klass = p.klass(module, node.value.value)
                if (
                    klass is not None
                    and klass.place.layer in ("domain", "application")
                    and any(a.startswith("enum.") for a in p.ancestors(klass))
                ):
                    found.append(
                        Finding(module.where(node), f"{module.dotted} publishes {klass.name} by its member name")
                    )
    return found


@rule("DCA-HEX-018")
def hex_018(p: Project) -> list[Finding]:
    return [
        Finding(
            module.where(function),
            f"the handler {function.name} sits in {module.dotted}, outside the incoming adapters",
        )
        for module, function, _, _ in handlers(p)
        if module.place.layer != "incoming"
    ]


def drives_an_input_port(p: Project, klass: Klass) -> bool:
    return any(p.has(k, "InputPort") for _, k in named_classes(p, klass.module) if k.qualname != klass.qualname) or any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute"
        for n in ast.walk(klass.node)
    )


@rule("DCA-HEX-019")
def hex_019(p: Project) -> list[Finding]:
    found = []
    for klass in p.with_role("OutputPort"):
        if klass.is_protocol or p.roles(klass) & {"Repository", "Store"} or klass.place.layer == "outgoing":
            continue
        if klass.place.layer == "root" and drives_an_input_port(p, klass):
            continue
        found.append(
            Finding(
                klass.where(),
                f"{klass.name} implements an output port in {klass.module.dotted}, outside the outgoing adapters",
            )
        )
    return found


ROLE_QUESTIONS = (
    "has_role",
    "has_any_role",
    "has_authority",
    "has_any_authority",
    "is_in_role",
    "is_user_in_role",
    "has_perm",
    "has_perms",
)


@rule("DCA-HEX-020")
def hex_020(p: Project) -> list[Finding]:
    if not p.layout.authorization_decorators:
        return []
    found = []
    for module in p.in_layer("incoming"):
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ROLE_QUESTIONS:
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} asks {node.func.attr}() in its own code; "
                        "a claims-only check is declared on the route",
                    )
                )
    return found


@rule("DCA-STR-005")
def str_005(p: Project) -> list[Finding]:
    return [
        Finding(
            k.where(),
            f"the open host service {k.name} sits in {k.module.dotted}, neither in an api package "
            "nor in an incoming adapter",
        )
        for k in p.with_role("OpenHostService")
        if k.place.layer not in ("api", "incoming")
    ]


@rule("DCA-STR-007")
def str_007(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the integration event {k.name} sits in {k.module.dotted}, outside api.events")
        for k in p.with_role("IntegrationEvent")
        if not (k.place.layer == "api" and k.place.sub == "events")
    ]


@rule("DCA-STR-008")
def str_008(p: Project) -> list[Finding]:
    found = []
    for event in p.with_role("IntegrationEvent"):
        found += [
            Finding(event.module.where(f.line), f"{event.name}.{f.name} is a mutable collection")
            for f in p.mutable_fields(event)
        ]
        found += [
            Finding(event.module.where(n), f"{event.name}.{name} changes its state") for name, n in p.mutators(event)
        ]
    return found


@rule("DCA-STR-010")
def str_010(p: Project) -> list[Finding]:
    return []


@rule("DCA-STR-013")
def str_013(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"{k.name} in {k.module.dotted} does not extend IntegrationEvent")
        for k in p.classes.values()
        if k.place.layer == "api"
        and k.place.sub == "events"
        and not p.has(k, "IntegrationEvent")
        and not any(a.startswith("enum.") for a in p.ancestors(k))
    ]


def decorator_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out = []
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = dotted_name(target)
        if name:
            out.append(name)
    return out
