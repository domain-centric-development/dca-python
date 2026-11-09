"""Failure rules: which exception sits where, what it carries, who raises it, and who translates it; closed results."""

from __future__ import annotations

import ast

from dca_rules.model import BB, Klass, Module, Project
from dca_rules.rules import Checked, Finding, rule
from dca_rules.rules.advanced import framework_metadata
from dca_rules.rules.hexagonal import named_classes

PORT_FAILURES = {"UseCaseException", "OutputPortException"}
CLASSIFICATION = {"PortException", "InputPortException"}
TRANSPORT = ("Http", "HTTP", "StatusCode", "ResponseStatus", "Response")


def is_exception(p: Project, klass: Klass) -> bool:
    ancestors = p.ancestors(klass)
    return (
        "builtins.Exception" in ancestors
        or "builtins.BaseException" in ancestors
        or bool(p.roles(klass) & {"DomainException", "PortException"})
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


@rule("DCA-ERR-007")
def err_007(p: Project) -> Checked:
    found = []
    selected = failures(p)
    for failure in selected:
        for field in failure.fields:
            names = p.type_names(failure.module, field.annotation)
            held = [n.rsplit(".", 1)[-1] for n in names if n == "builtins.str"] + [
                k.name for k in p.type_classes(failure.module, field.annotation) if p.has(k, "Entity")
            ]
            if held:
                found.append(
                    Finding(
                        failure.module.where(field.line),
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
        for call, klass in p.constructions(module):
            if p.has(klass, "DomainException"):
                found.append(
                    Finding(
                        module.where(call),
                        f"{module.dotted} constructs the domain exception {klass.name}; only the domain does",
                    )
                )
    return Checked(len(p.with_role("DomainException")), found)
