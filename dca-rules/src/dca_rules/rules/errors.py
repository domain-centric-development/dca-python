"""Failure rules: which exception sits where, what it carries, who raises it, and who translates it; closed results."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Iterator

from dca_rules.model import BB, Klass, Module, Project, annotation_expr
from dca_rules.rules import Checked, Finding, rule
from dca_rules.rules.advanced import framework_metadata
from dca_rules.rules.hexagonal import named_classes

PORT_FAILURES = {"UseCaseException", "OutputPortException"}
CLASSIFICATION = {"PortException", "InputPortException"}
TRANSPORT = ("Http", "HTTP", "StatusCode", "ResponseStatus", "ResponseEntity")


def _builtin_exception(name: str) -> bool:
    """`builtins.ValueError`, `builtins.KeyError`, ...: an exception class of the standard library's builtins."""
    if not name.startswith("builtins."):
        return False
    found = getattr(builtins, name.removeprefix("builtins."), None)
    return isinstance(found, type) and issubclass(found, BaseException)


def is_exception(p: Project, klass: Klass) -> bool:
    """A class that extends any built-in exception (`Exception`, `ValueError`, ...) or carries a failure role."""
    return any(_builtin_exception(a) for a in p.ancestors(klass)) or bool(
        p.roles(klass) & {"DomainException", "PortException"}
    )


def failures(p: Project) -> list[Klass]:
    return [k for k in p.classes.values() if p.roles(k) & {"DomainException", "PortException"}]


@rule("DCA-ERR-001")
def err_001(p: Project) -> Checked:
    selected = [k for k in p.classes_in("domain") if is_exception(p, k)]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the exception {k.name} in the domain does not extend DomainException")
            for k in selected
            if not p.has(k, "DomainException")
        ],
    )


@rule("DCA-ERR-002")
def err_002(p: Project) -> Checked:
    selected = failures(p)
    found = [
        Finding(k.where(), f"the domain exception {k.name} sits in {k.module.dotted}, outside the domain")
        for k in p.with_role("DomainException")
        if k.place.layer != "domain"
    ]
    found += [
        Finding(k.where(), f"the port exception {k.name} sits in {k.module.dotted}, outside the application")
        for k in p.with_role("PortException")
        if k.place.layer != "application"
    ]
    return Checked(len(selected), found)


@rule("DCA-ERR-003")
def err_003(p: Project) -> Checked:
    selected = [k for k in p.classes_in("application") if is_exception(p, k)]
    return Checked(
        len(selected),
        [
            Finding(
                k.where(),
                f"the exception {k.name} in the application extends neither UseCaseException nor OutputPortException",
            )
            for k in selected
            if not p.has(k, "DomainException") and not p.roles(k) & PORT_FAILURES
        ],
    )


@rule("DCA-ERR-004")
def err_004(p: Project) -> Checked:
    selected = failures(p)
    return Checked(
        len(selected),
        [
            Finding(k.module.where(node), f"the failure {k.name} carries {name}")
            for k in selected
            for node, name in framework_metadata(p, k)
        ],
    )


@rule("DCA-ERR-005")
def err_005(p: Project) -> Checked:
    selected = failures(p)
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the failure {k.name} is named in transport vocabulary")
            for k in selected
            if any(t in k.name for t in TRANSPORT)
        ],
    )


def alias_members(p: Project, module: Module, node: ast.expr | None) -> list[Klass]:
    """The classes of a union, through a `type X = A | B` alias or an `X = A | B` assignment."""
    if node is None:
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return alias_members(p, module, node.left) + alias_members(p, module, node.right)
    if isinstance(node, ast.Subscript) and (p.resolve(module, node.value) or "").endswith("Union"):
        elts = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        return [k for e in elts for k in alias_members(p, module, e)]
    klass = p.klass(module, node)
    if klass is not None:
        return [klass]
    name = p.resolve(module, node)
    if name is None:
        return []
    owner, _, attr = name.rpartition(".")
    home = p.modules.get(owner)
    target = home.defined.get(attr) if home else None
    if isinstance(target, ast.TypeAlias):
        return alias_members(p, home, target.value)  # type: ignore[arg-type]
    if isinstance(target, (ast.Assign, ast.AnnAssign)) and isinstance(target.value, (ast.BinOp, ast.Subscript)):
        return alias_members(p, home, target.value)  # type: ignore[arg-type]
    return []


def closed_results(p: Project) -> dict[str, tuple[Klass, list[Klass]]]:
    """{the input port's name: (port, the cases of its closed result)} for every input port that answers with a
    union of two or more classes."""
    out = {}
    for port in p.with_role("InputPort"):
        if not port.is_protocol:
            continue
        answer: ast.expr | None = None
        for base in port.node.bases:
            if isinstance(base, ast.Subscript) and (p.resolve(port.module, base.value) or "") in (
                f"{BB}.UseCase",
                f"{BB}.AsyncUseCase",
            ):
                elts = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
                answer = elts[-1] if len(elts) == 2 else None
        if answer is None and "execute" in port.methods:
            answer = port.methods["execute"].returns
        cases = [c for c in alias_members(p, port.module, answer) if not is_exception(p, c)]
        if len(cases) > 1:
            out[port.name] = (port, cases)
    return out


@rule("DCA-ERR-006")
def err_006(p: Project) -> Checked:
    """Selects the incoming adapters that drive an input port - where the project has a failure or a refusal to
    translate at all."""
    cases = {c.qualname for _, (_, cs) in closed_results(p).items() for c in cs}
    if not failures(p) and not cases:
        return Checked(0, [])
    found = []
    selected = 0
    for module in p.in_layer("incoming"):
        named = list(named_classes(p, module))
        if not any(p.has(k, "InputPort") for _, k in named):
            continue
        selected += 1
        translates = any(p.roles(k) & {"DomainException", "UseCaseException"} or k.qualname in cases for _, k in named)
        if not translates:
            found.append(
                Finding(
                    module.where(1),
                    f"{module.dotted} drives a use case and translates none of its failures or refusals",
                )
            )
        for node, name in p.refs(module, module.tree):
            if name in {f"{BB}.{c}" for c in CLASSIFICATION | {"OutputPortException"}}:
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} handles {name.rsplit('.', 1)[-1]} as such: every outcome the same way",
                    )
                )
    return Checked(selected, found)


#: What a failure may carry beside ids and values: numbers, yes/no, points and spans of time, and what holds them.
CARRIED = {
    "builtins.int",
    "builtins.float",
    "builtins.bool",
    "builtins.complex",
    "decimal.Decimal",
    "fractions.Fraction",
    "datetime.datetime",
    "datetime.date",
    "datetime.time",
    "datetime.timedelta",
    "builtins.None",
    "None",
}
CONTAINERS = {"builtins.list", "builtins.tuple", "builtins.set", "builtins.frozenset", "builtins.dict", "builtins.type"}


def _carried(p: Project, name: str) -> bool:
    """A type a failure may carry: an id or a value, an enum, a number, a point or span of time - or a container or a
    typing construct, which is looked through."""
    if name in CARRIED or name in CONTAINERS or name.startswith(("typing.", "collections.abc.")):
        return True
    roles = p.name_roles(name)
    if roles & {"Id", "Value"}:
        return True
    klass = p.classes.get(name)
    return klass is not None and any(a.startswith("enum.") for a in p.ancestors(klass))


@rule("DCA-ERR-007")
def err_007(p: Project) -> Checked:
    """Informational: lists every field of a failure that carries a string, an entity or any other type that is no id,
    no value, no number, no enum and no date or time - containers looked through; the fields of role-less bases
    included."""
    found = []
    selected = failures(p)
    for failure in selected:
        for field in p.member_fields(failure):
            names = p.type_names(field.module, annotation_expr(field.annotation))
            held = sorted({n.rsplit(".", 1)[-1] for n in names if not _carried(p, n)})
            if held:
                found.append(
                    Finding(
                        field.module.where(field.line),
                        f"{failure.name}.{field.name} carries {', '.join(held)}; carry ids and figures",
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-ERR-008")
def err_008(p: Project) -> Checked:
    selected = sorted(closed_results(p).items())
    return Checked(
        len(selected),
        [
            Finding(
                port.where(),
                f"the closed result of {name} ({', '.join(c.name for c in cases)}) has no case marked Refusal",
            )
            for name, (port, cases) in selected
            if not any(p.has(c, "Refusal") for c in cases)
        ],
    )


@rule("DCA-ERR-009")
def err_009(p: Project) -> Checked:
    """Selects the domain exceptions, and checks every place that builds one."""
    found = []
    for module in p.modules.values():
        if module.place.layer == "domain":
            continue
        built: list[tuple[ast.AST, Klass]] = list(p.constructions(module))
        # `raise Gone` raises the class: Python constructs it.
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, (ast.Name, ast.Attribute)):
                klass = p.klass(module, node.exc)
                if klass is not None:
                    built.append((node, klass))
        for node, klass in built:
            if p.has(klass, "DomainException"):
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} constructs the domain exception {klass.name}; only the domain does",
                    )
                )
    return Checked(len(p.with_role("DomainException")), found)


CATCH_ALL = {"builtins.Exception", "builtins.BaseException"}
PORTS = {"InputPort", "OutputPort"}


def _scopes(p: Project, module: Module) -> Iterator[tuple[ast.FunctionDef | ast.AsyncFunctionDef, Klass | None]]:
    """Every module-level function and every method of a class of the module, with its class."""
    for statement in module.tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield statement, None
    for klass in p.classes.values():
        if klass.module is module:
            for method in klass.methods.values():
                yield method, klass


def _port_call(
    body: list[ast.stmt], names: dict[str, frozenset[str]], fields: dict[str, frozenset[str]]
) -> ast.Call | None:
    """The first call in a try part of a method on a port: a parameter or annotated local, or `self.<field>`."""
    for statement in body:
        for node in ast.walk(statement):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            receiver = node.func.value
            if isinstance(receiver, ast.Name) and names.get(receiver.id):
                return node
            if (
                isinstance(receiver, ast.Attribute)
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "self"
                and fields.get(receiver.attr, frozenset()) & PORTS
            ):
                return node
    return None


def _catches_all(p: Project, module: Module, handler: ast.ExceptHandler) -> str | None:
    """What a handler catches that is every failure, or the port failures' common base; None when it names its
    failures."""
    if handler.type is None:
        return "everything (a bare except)"
    caught = list(handler.type.elts) if isinstance(handler.type, ast.Tuple) else [handler.type]
    for node in caught:
        name = p.resolve(module, node) or ""
        if name in CATCH_ALL:
            return name.removeprefix("builtins.")
        roles = p.name_roles(name)
        if "PortException" in roles and not roles & {"OutputPortException", "UseCaseException"}:
            return name.rsplit(".", 1)[-1]
    return None


def _passes_on(handler: ast.ExceptHandler) -> bool:
    """The handler hands the caught failure on unchanged: it ends in a bare `raise` or `raise <the caught name>`
    without a cause, and no `return`, `break` or `continue` of its own leaves it another way - it may clean up first."""
    if not handler.body:
        return False
    last = handler.body[-1]
    if not isinstance(last, ast.Raise) or last.cause is not None:
        return False
    if last.exc is not None and not (isinstance(last.exc, ast.Name) and last.exc.id == handler.name):
        return False

    def exits(node: ast.AST) -> bool:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            return False
        if isinstance(node, (ast.Return, ast.Break, ast.Continue)):
            return True
        return any(exits(child) for child in ast.iter_child_nodes(node))

    return not any(exits(statement) for statement in handler.body)


@rule("DCA-ERR-010")
def err_010(p: Project) -> Checked:
    """Selects every try statement in the application and the incoming adapters whose try part calls a method on an
    input or output port. A catch-all handler that hands the failure on unchanged, after cleaning up, passes."""
    selected = 0
    found = []
    for module in p.in_layer("application", "incoming"):
        for scope, klass in _scopes(p, module):
            names = {n: roles & PORTS for n, roles in p.scope_types(klass, module, scope).items() if roles & PORTS}
            fields = p.self_types(klass) if klass is not None else {}
            for node in ast.walk(scope):
                if not isinstance(node, (ast.Try, ast.TryStar)):
                    continue
                call = _port_call(node.body, names, fields)
                if call is None:
                    continue
                selected += 1
                target = ast.unparse(call.func)
                for handler in node.handlers:
                    caught = _catches_all(p, module, handler)
                    if caught is not None and not _passes_on(handler):
                        found.append(
                            Finding(
                                module.where(handler),
                                f"{scope.name} catches {caught} around {target}; catch the failure the port "
                                "declares by its own type",
                            )
                        )
    return Checked(selected, sorted(set(found)))
