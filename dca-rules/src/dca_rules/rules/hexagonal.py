"""Hexagonal and strategic rules over what the source names: ports, adapters, handlers, published contracts."""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Callable, Iterator

from dca_rules.model import BB, Klass, Module, Project, dotted_name, parameters
from dca_rules.rules import Checked, Finding, rule


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


def _names(p: Project, layer: str, test: str, what: str, predicate: Callable[[Klass], bool]) -> Checked:
    found = []
    selected = p.in_layer(layer)
    for module in selected:
        seen = set()
        for node, klass in named_classes(p, module):
            if klass.qualname in seen or not predicate(klass):
                continue
            seen.add(klass.qualname)
            found.append(Finding(module.where(node), f"{module.dotted} names {test} {klass.name}: {what}"))
    return Checked(len(selected), found)


def is_use_case(p: Project, klass: Klass) -> bool:
    return p.has(klass, "InputPort") and not klass.is_protocol


@rule("DCA-HEX-003")
def hex_003(p: Project) -> Checked:
    return _names(
        p, "incoming", "the repository", "an incoming adapter drives an input port", lambda k: p.has(k, "Repository")
    )


@rule("DCA-HEX-008")
def hex_008(p: Project) -> Checked:
    selected = [
        k
        for k in p.classes.values()
        if not k.is_protocol and (k.name.endswith(p.layout.repository_suffix) or p.has(k, "Repository"))
    ]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the class {k.name} sits in {k.module.dotted}, outside the outgoing adapters")
            for k in selected
            if k.name.endswith(p.layout.repository_suffix) and k.place.layer != "outgoing"
        ],
    )


@rule("DCA-HEX-009")
def hex_009(p: Project) -> Checked:
    selected = [k for k in p.classes_in("application") if k.place.shared and k.is_protocol]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the protocol {k.name} in application.{p.layout.shared} does not extend OutputPort")
            for k in selected
            if not p.has(k, "OutputPort")
        ],
    )


@rule("DCA-HEX-010")
def hex_010(p: Project) -> Checked:
    selected = [k for k in p.with_role("OutputPort") if k.is_protocol]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the output port {k.name} is declared in the domain")
            for k in selected
            if k.place.layer == "domain"
        ],
    )


@rule("DCA-HEX-011")
def hex_011(p: Project) -> Checked:
    return _names(
        p, "incoming", "the use case", "an incoming adapter depends on the input port", lambda k: is_use_case(p, k)
    )


@rule("DCA-HEX-012")
def hex_012(p: Project) -> Checked:
    return _names(
        p,
        "incoming",
        "the domain service",
        "an incoming adapter drives an input port",
        lambda k: p.has(k, "DomainService"),
    )


@rule("DCA-HEX-013")
def hex_013(p: Project) -> Checked:
    return _names(
        p,
        "outgoing",
        "the input port",
        "an outgoing adapter is driven, it drives nothing",
        lambda k: p.has(k, "InputPort"),
    )


def _decorated(method: ast.FunctionDef | ast.AsyncFunctionDef, *names: str) -> bool:
    return any(dotted_name(d.func if isinstance(d, ast.Call) else d) in names for d in method.decorator_list)


def _changes_self(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(method):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            while isinstance(target, (ast.Attribute, ast.Subscript)):
                if isinstance(target.value, ast.Name) and target.value.id == "self":
                    return True
                target = target.value
    return False


def commands_of(p: Project, root: Klass) -> set[str]:
    """The methods of an aggregate root, its own and inherited from project classes, that change its state: a public
    instance method that assigns to `self` or is declared to return `None`. Properties, class and static methods are
    queries or constructors."""
    owners = [root] + [p.classes[a] for a in p.ancestors(root) if a in p.classes]
    out: set[str] = set()
    for owner in owners:
        for name, method in owner.methods.items():
            if name.startswith("_") or _decorated(method, "property", "classmethod", "staticmethod"):
                continue
            returns_none = isinstance(method.returns, ast.Constant) and method.returns.value is None
            if returns_none or _changes_self(method):
                out.add(name)
    return out


class _RootHolders:
    """The names in one scope of an outgoing adapter that hold an aggregate root: parameters and locals annotated with
    one, a construction or a factory call of one, a call declared to return one, the loop variable over a name that
    holds roots, and `self.<attr>` typed with one."""

    def __init__(self, p: Project, module: Module, attributes: dict[str, Klass], held: dict[str, Klass]) -> None:
        self.p = p
        self.module = module
        self.attributes = attributes
        self.held = held
        self.names: dict[str, Klass] = {}

    def root(self, annotation: ast.expr | None, module: Module | None = None) -> Klass | None:
        for klass in self.p.type_classes(module or self.module, annotation):
            if self.p.has(klass, "AggregateRoot"):
                return klass
        return None

    def returned(self, node: ast.expr | None) -> Klass | None:
        """The aggregate root a call returns by its declaration: a method of a class named or held in
        `self.<attr>`, or a function of the project."""
        if isinstance(node, ast.Await):
            node = node.value
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if isinstance(func, ast.Attribute):
            owner = self.p.klass(self.module, func.value)
            if owner is None and isinstance(func.value, ast.Attribute) and isinstance(func.value.value, ast.Name):
                owner = self.held.get(func.value.attr) if func.value.value.id == "self" else None
            if owner is not None:
                for klass in [owner] + [self.p.classes[a] for a in self.p.ancestors(owner) if a in self.p.classes]:
                    method = klass.methods.get(func.attr)
                    if method is not None:
                        return self.root(method.returns, klass.module)
        name = self.p.resolve(self.module, func)
        if name:
            where, _, function = name.rpartition(".")
            module = self.p.modules.get(where)
            defined = module.defined.get(function) if module is not None else None
            if isinstance(defined, (ast.FunctionDef, ast.AsyncFunctionDef)) and module is not None:
                return self.root(defined.returns, module)
        return None

    def built(self, node: ast.expr | None) -> Klass | None:
        if not isinstance(node, ast.Call):
            return None
        klass = self.p.klass(self.module, node.func)
        if klass is None and isinstance(node.func, ast.Attribute):
            klass = self.p.klass(self.module, node.func.value)
            method = klass.methods.get(node.func.attr) if klass is not None else None
            if method is None or not _decorated(method, "classmethod", "staticmethod"):
                klass = None
        return klass if klass is not None and self.p.has(klass, "AggregateRoot") else None

    def holder(self, node: ast.expr) -> Klass | None:
        if isinstance(node, ast.Name):
            return self.names.get(node.id)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
            return self.attributes.get(node.attr)
        return None

    def bind(self, node: ast.AST) -> None:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            klass = self.root(node.annotation) or self.built(node.value) or self.returned(node.value)
            if klass is not None:
                self.names[node.target.id] = klass
        elif isinstance(node, ast.Assign):
            klass = self.built(node.value) or self.returned(node.value)
            if klass is not None:
                self.names.update((t.id, klass) for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
            klass = self.holder(node.iter) if isinstance(node.iter, (ast.Name, ast.Attribute)) else None
            if klass is not None:
                self.names[node.target.id] = klass

    def calls(self, function: ast.FunctionDef | ast.AsyncFunctionDef) -> Iterator[tuple[ast.Call, Klass, str]]:
        for argument in parameters(function):
            klass = self.root(argument.annotation)
            if klass is not None:
                self.names[argument.arg] = klass
        for node in ast.walk(function):
            self.bind(node)
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                klass = self.holder(node.func.value)
                if klass is not None:
                    yield node, klass, node.func.attr


@rule("DCA-HEX-021")
def hex_021(p: Project) -> Checked:
    """Selects every function and method of the outgoing adapters, where the project has an aggregate root."""
    if not p.with_role("AggregateRoot"):
        return Checked(0, [])
    found = []
    selected = 0
    commands: dict[str, set[str]] = {}
    for module in p.in_layer("outgoing"):
        scopes: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, dict[str, Klass], dict[str, Klass]]] = []
        for statement in module.tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                scopes.append((statement, {}, {}))
        for klass in p.classes.values():
            if klass.module is not module:
                continue
            attributes: dict[str, Klass] = {}
            held: dict[str, Klass] = {}
            for field in klass.fields:
                for typed in p.type_classes(module, field.annotation):
                    held.setdefault(field.name, typed)
                    if p.has(typed, "AggregateRoot"):
                        attributes[field.name] = typed
            scopes += [(method, attributes, held) for method in klass.methods.values()]
        selected += len(scopes)
        for function, attributes, held in scopes:
            for call, root, name in _RootHolders(p, module, attributes, held).calls(function):
                if root.qualname not in commands:
                    commands[root.qualname] = commands_of(p, root)
                if name in commands[root.qualname]:
                    found.append(
                        Finding(
                            module.where(call),
                            f"{function.name} calls {root.name}.{name}, which changes the aggregate; an outgoing "
                            "adapter stores and loads what the aggregate holds, the application changes it",
                        )
                    )
    return Checked(selected, found)


HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


@dataclasses.dataclass
class Handler:
    """A function or method that answers an HTTP method: registered by a router decorator, or a method of a
    class-based view named after the HTTP method."""

    module: Module
    function: ast.FunctionDef | ast.AsyncFunctionDef
    method: str
    view: Klass | None = None


def _registered(p: Project, module: Module, decorator: ast.expr) -> str | None:
    """The HTTP method a router decorator registers its function for: `<router>.<method>(path, ...)` or an imported
    `<method>(path, ...)` of the configured router methods, the path a literal or any expression; route/api_route
    by its methods=[...]."""
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if isinstance(func, ast.Attribute):
        method = func.attr
    elif isinstance(func, ast.Name) and p.is_framework(p.resolve(module, func) or ""):
        method = func.id
    else:
        return None
    path = decorator.args[0] if decorator.args else next((k.value for k in decorator.keywords if k.arg == "path"), None)
    if method not in p.layout.router_methods or path is None:
        return None
    if isinstance(path, ast.Constant) and not isinstance(path.value, str):
        return None
    if method in ("route", "api_route"):
        methods = next((k.value for k in decorator.keywords if k.arg == "methods"), None)
        names = [e.value for e in getattr(methods, "elts", []) if isinstance(e, ast.Constant)]
        method = "get" if not names or "GET" in names else str(names[0]).lower()
    return method


def is_view(p: Project, klass: Klass) -> bool:
    return any(any(a == b or a.startswith(b + ".") for b in p.layout.view_bases) for a in p.ancestors(klass))


def handlers(p: Project) -> Iterator[Handler]:
    """Every handler: a function a router decorator registers, and the HTTP-method methods of a class-based view."""
    for module in p.modules.values():
        for node in ast.walk(module.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                method = _registered(p, module, decorator)
                if method is not None:
                    yield Handler(module, node, method)
                    break
    for klass in p.classes.values():
        if is_view(p, klass):
            for name, function in klass.methods.items():
                if name in HTTP_METHODS and not any(_registered(p, klass.module, d) for d in function.decorator_list):
                    yield Handler(klass.module, function, name, klass)


def _takes_command(p: Project, port: Klass) -> bool:
    """An input port whose input is a command: `I` of its `UseCase[I, O]`, or a parameter of its execute."""
    for klass in [port, *p.lineage(port)]:
        for base in klass.node.bases:
            if isinstance(base, ast.Subscript) and p.resolve(klass.module, base.value) in (
                f"{BB}.UseCase",
                f"{BB}.AsyncUseCase",
            ):
                arguments = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
                if any(k.name.endswith("Command") for k in p.type_classes(klass.module, arguments[0])):
                    return True
        execute = klass.methods.get("execute")
        if execute is not None and any(
            k.name.endswith("Command") for a in parameters(execute) for k in p.type_classes(klass.module, a.annotation)
        ):
            return True
    return False


def _bodies(p: Project, handler: Handler) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    """The handler, then what it calls of its own: a function of its module, or a method of its view."""
    out: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = [(handler.function, "")]
    for node in ast.walk(handler.function):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        found: ast.AST | None = None
        if isinstance(func, ast.Name):
            found = handler.module.defined.get(func.id)
        elif (
            handler.view is not None
            and isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            found = handler.view.methods.get(func.attr)
        if isinstance(found, (ast.FunctionDef, ast.AsyncFunctionDef)) and all(found is not b for b, _ in out):
            out.append((found, f", through {found.name},"))
    return out


@rule("DCA-HEX-014")
def hex_014(p: Project) -> Checked:
    """Selects the handlers of GET. None - nor a function of its module or a method of its view it calls - names a
    command class of the application (built, taken or annotated) or calls an input port that takes a command."""
    found: dict[tuple[str, str], Finding] = {}
    selected = [h for h in handlers(p) if h.method == "get"]
    for handler in selected:
        module = handler.module
        fields = {}
        if handler.view is not None:
            fields = {f.name: [k for k in p.type_classes(f.module, f.annotation)] for f in p.all_fields(handler.view)}
        for body, via in _bodies(p, handler):
            for node, name in p.refs(module, body):
                klass = p.classes.get(name)
                if klass is not None and klass.name.endswith("Command") and klass.place.layer == "application":
                    where = module.where(node)
                    found.setdefault(
                        (where, klass.name),
                        Finding(where, f"the GET handler {handler.function.name}{via} drives the command {klass.name}"),
                    )
            ports: dict[str, Klass] = {}
            for item in ast.walk(body):
                named: list[tuple[str, ast.expr | None]] = []
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    named = [(a.arg, a.annotation) for a in parameters(item)]
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    named = [(item.target.id, item.annotation)]
                for local, annotation in named:
                    for klass in p.type_classes(module, annotation):
                        if p.has(klass, "InputPort") and _takes_command(p, klass):
                            ports[local] = klass
            for item in ast.walk(body):
                if not (isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)):
                    continue
                receiver = item.func.value
                port = ports.get(receiver.id) if isinstance(receiver, ast.Name) else None
                if (
                    port is None
                    and isinstance(receiver, ast.Attribute)
                    and isinstance(receiver.value, ast.Name)
                    and receiver.value.id == "self"
                ):
                    port = next(
                        (k for k in fields.get(receiver.attr, []) if p.has(k, "InputPort") and _takes_command(p, k)),
                        None,
                    )
                if port is not None:
                    where = module.where(item)
                    found.setdefault(
                        (where, port.name),
                        Finding(
                            where,
                            f"the GET handler {handler.function.name}{via} calls {item.func.attr} on {port.name}, "
                            "an input port that takes a command",
                        ),
                    )
    return Checked(len(selected), list(found.values()))


@rule("DCA-HEX-016")
def hex_016(p: Project) -> Checked:
    found = []
    selected = p.in_layer("incoming", "outgoing", "adapter")
    for module in selected:
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
    return Checked(len(selected), found)


@rule("DCA-HEX-018")
def hex_018(p: Project) -> Checked:
    """Selects the handlers: the functions router decorators register, and the class-based views (once each)."""
    selected: dict[int, tuple[Module, ast.AST, str]] = {}
    for h in handlers(p):
        node: ast.AST = h.view.node if h.view is not None else h.function
        name = h.view.name if h.view is not None else h.function.name
        selected.setdefault(id(node), (h.module, node, name))
    return Checked(
        len(selected),
        [
            Finding(module.where(node), f"the handler {name} sits in {module.dotted}, outside the incoming adapters")
            for module, node, name in selected.values()
            if module.place.layer != "incoming"
        ],
    )


def drives_an_input_port(p: Project, klass: Klass) -> bool:
    """The class itself depends on an input port: names a class with the InputPort role in its fields, its methods'
    parameters or their bodies, or calls execute."""
    named = [k for f in p.all_fields(klass) for k in p.type_classes(f.module, f.annotation)]
    for method in klass.methods.values():
        named += [k for a in parameters(method) for k in p.type_classes(klass.module, a.annotation)]
        named += [p.classes[n] for _, n in p.refs(klass.module, method) if n in p.classes]
    return any(p.has(k, "InputPort") for k in named if k.qualname != klass.qualname) or any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "execute"
        for n in ast.walk(klass.node)
    )


@rule("DCA-HEX-019")
def hex_019(p: Project) -> Checked:
    """Selects every implementation of an output port, repositories and stores included; a class in an
    infrastructure package - a context's or the composition root - that itself drives an input port is the bridge
    that hands an output port a second use case: wiring, not selected."""
    found = []
    selected = [
        k
        for k in p.with_role("OutputPort")
        if not k.is_protocol and not (k.place.layer in ("root", "infrastructure") and drives_an_input_port(p, k))
    ]
    for klass in selected:
        if klass.place.layer == "outgoing":
            continue
        found.append(
            Finding(
                klass.where(),
                f"{klass.name} implements an output port in {klass.module.dotted}, outside the outgoing adapters",
            )
        )
    return Checked(len(selected), found)


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
def hex_020(p: Project) -> Checked:
    """Selects the incoming adapters; nothing where the layout names no declarative authorization to advise."""
    if not p.layout.authorization_decorators:
        return Checked(0, [])
    found = []
    selected = p.in_layer("incoming")
    for module in selected:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ROLE_QUESTIONS:
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} asks {node.func.attr}() in its own code; "
                        "a claims-only check is declared on the route",
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-STR-005")
def str_005(p: Project) -> Checked:
    """Selects the classes that carry the OpenHostService role and the modules that declare one: an open host
    service of functions marks its package with `__dca__ = OpenHostService()`."""
    classes = p.with_role("OpenHostService")
    modules = p.module_markers("OpenHostService")
    found = [
        Finding(
            k.where(),
            f"the open host service {k.name} sits in {k.module.dotted}, neither in an api package "
            "nor in an incoming adapter",
        )
        for k in classes
        if k.place.layer not in ("api", "incoming")
    ]
    found += [
        Finding(
            module.where(call),
            f"{module.dotted} declares an open host service and sits neither in an api package "
            "nor in an incoming adapter",
        )
        for module, call in modules
        if module.place.layer not in ("api", "incoming")
    ]
    return Checked(len(classes) + len(modules), found)


@rule("DCA-STR-007")
def str_007(p: Project) -> Checked:
    selected = p.with_role("IntegrationEvent")
    return Checked(
        len(selected),
        [
            Finding(
                k.where(),
                f"the integration event {k.name} sits in {k.module.dotted}, outside a context's {p.layout.events} "
                "package - one context's published contract, never the shared kernel's",
            )
            for k in selected
            if not (k.place.layer == "events" and not k.place.kernel)
        ],
    )


@rule("DCA-STR-008")
def str_008(p: Project) -> Checked:
    found = []
    selected = p.with_role("IntegrationEvent")
    for event in selected:
        found += [
            Finding(f.module.where(f.line), f"{event.name}.{f.name} is a mutable collection")
            for f in p.mutable_fields(event)
        ]
        found += [
            Finding(home.where(n), f"{event.name}.{name} changes its state") for name, n, home in p.mutators(event)
        ]
    return Checked(len(selected), found)


@rule("DCA-STR-010", doctrine=True)
def str_010(p: Project) -> Checked:
    return Checked(0, [])


@rule("DCA-STR-013")
def str_013(p: Project) -> Checked:
    selected = [k for k in p.classes.values() if k.place.layer == "events"]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} in {k.module.dotted} does not extend IntegrationEvent")
            for k in selected
            if not p.has(k, "IntegrationEvent") and not any(a.startswith("enum.") for a in p.ancestors(k))
        ],
    )


def decorator_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    out = []
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = dotted_name(target)
        if name:
            out.append(name)
    return out
