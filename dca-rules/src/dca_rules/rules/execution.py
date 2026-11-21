"""How code runs: a synchronous domain (DCA-ONI-004), an application without persistence or transaction APIs
(DCA-LAY-008), and listeners that drive a use case only after the commit (DCA-HEX-017)."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from dca_rules.model import Klass, Module, Project, dotted_name, parameters
from dca_rules.rules import Checked, Finding, rule

ASYNC_NODES = (ast.Await, ast.AsyncFor, ast.AsyncWith)


def _prefixed(name: str | None, prefixes: tuple[str, ...]) -> bool:
    return name is not None and any(name == p or name.startswith(p + ".") for p in prefixes)


def _asynchronous_roles(p: Project, klass: Klass) -> bool:
    """A domain gateway answers asynchronously when its adapter does; a domain service that awaits it is async too."""
    return p.has(klass, "DomainGateway") or p.has(klass, "DomainService")


def _functions(tree: ast.AST) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


@rule("DCA-ONI-004")
def oni_004(p: Project) -> Checked:
    found = []
    selected = p.in_layer("domain")
    for module in selected:
        exempt: set[int] = set()
        for klass in (k for k in p.classes.values() if k.module is module and _asynchronous_roles(p, k)):
            exempt.update(id(n) for n in ast.walk(klass.node))
        for line, target in p.import_targets(module):
            if _prefixed(target, p.layout.async_runtimes):
                found.append(Finding(module.where(line), f"{module.dotted} imports {target}, an asynchronous runtime"))
        for node in ast.walk(module.tree):
            if id(node) in exempt:
                continue
            if isinstance(node, ast.AsyncFunctionDef):
                found.append(Finding(module.where(node.lineno), f"{node.name} is async; the domain is synchronous"))
            elif isinstance(node, ASYNC_NODES):
                found.append(Finding(module.where(node.lineno), "the domain awaits; it is synchronous"))
            elif isinstance(node, (ast.Name, ast.Attribute)) and _prefixed(
                p.resolve(module, node), p.layout.async_types
            ):
                found.append(
                    Finding(
                        module.where(node.lineno),
                        f"{dotted_name(node)} is an asynchronous type; only a domain gateway or a domain service may "
                        "answer asynchronously",
                    )
                )
    return Checked(len(selected), _unique(found))


def _unique(found: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    out = []
    for f in found:
        if (f.location, f.message) not in seen:
            seen.add((f.location, f.message))
            out.append(f)
    return out


@rule("DCA-LAY-008")
def lay_008(p: Project) -> Checked:
    found = []
    selected = p.in_layer("application")
    for module in selected:
        for line, target in p.import_targets(module):
            if _prefixed(target, p.layout.persistence_apis):
                found.append(
                    Finding(
                        module.where(line),
                        f"{module.dotted} imports {target}: the application reaches persistence through its output "
                        "ports and runs a transaction through TransactionBoundary",
                    )
                )
    return Checked(len(selected), found)


def _input_port(p: Project, module: Module, node: ast.AST | None) -> str | None:
    """The name of a class with the input-port role an annotation or an expression mentions."""
    for _, name in p.refs(module, node):
        klass = p.classes.get(name)
        if klass is not None and p.has(klass, "InputPort"):
            return klass.name
    return None


def _reaches_an_input_port(p: Project, klass: Klass) -> str | None:
    """A field typed with an input port, an `__init__` parameter typed with one, or a name of one in a method body."""
    for field in klass.fields:
        if named := _input_port(p, field.module, field.annotation):
            return named
    for method in klass.methods.values():
        for argument in parameters(method):
            if named := _input_port(p, klass.module, argument.annotation):
                return named
        for statement in method.body:
            if named := _input_port(p, klass.module, statement):
                return named
    return None


@rule("DCA-HEX-017")
def hex_017(p: Project) -> Checked:
    found = []
    listeners = [k for k in p.with_role("EventListener") if not k.is_protocol]
    selected = [k for k in listeners if not p.has(k, "TransactionalEventListener")]
    for klass in selected:
        if named := _reaches_an_input_port(p, klass):
            found.append(
                Finding(
                    klass.where(),
                    f"the listener {klass.name} reacts inside the publishing transaction and drives the input port "
                    f"{named}; a listener that drives a use case is a TransactionalEventListener, delivered after "
                    "the commit in a transaction of its own",
                )
            )
    functions = 0
    for module in p.modules.values():
        for function in _functions(module.tree):
            decorators = [p.resolve(module, d.func if isinstance(d, ast.Call) else d) for d in function.decorator_list]
            if not any(_prefixed(d, p.layout.listener_decorators) for d in decorators):
                continue
            functions += 1
            for statement in [*function.body, *(a.annotation for a in parameters(function) if a.annotation)]:
                if named := _input_port(p, module, statement):
                    found.append(
                        Finding(
                            module.where(function.lineno),
                            f"{function.name} listens inside the publishing transaction and drives the input port "
                            f"{named}; a listener that drives a use case runs after the commit",
                        )
                    )
                    break
    return Checked(len(selected) + functions, found)
