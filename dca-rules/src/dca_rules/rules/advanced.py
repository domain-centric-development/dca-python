"""Domain events, integration events, domain services, factories, specifications, and the framework metadata the
domain must not carry."""

from __future__ import annotations

import ast

from dca_rules.model import Klass, Project, parameters, public
from dca_rules.rules import Finding, rule
from dca_rules.rules.tactical import is_leaf

VERSION_FIELDS = ("schema_version", "event_version", "contract_version")


def framework_metadata(p: Project, klass: Klass) -> list[tuple[ast.AST, str]]:
    """Decorators and bases of a class that come from a configured framework."""
    out: list[tuple[ast.AST, str]] = [(node, name) for name, node in klass.decorators if p.is_framework(name)]
    out += [(klass.node, name) for name in klass.bases if p.is_framework(p.canonical(name))]
    for field in klass.fields:
        node = next((n for n in klass.node.body if isinstance(n, ast.AnnAssign) and n.lineno == field.line), None)
        if node is not None and isinstance(node.value, ast.Call):
            name = p.resolve(klass.module, node.value.func)
            if name and p.is_framework(name):
                out.append((node, name))
    return out


def _metadata(p: Project, classes: list[Klass], what: str) -> list[Finding]:
    return [
        Finding(k.module.where(node), f"the {what} {k.name} carries {name}")
        for k in classes
        for node, name in framework_metadata(p, k)
    ]


def in_domain(p: Project, role: str) -> list[Klass]:
    return [k for k in p.with_role(role) if k.place.layer == "domain"]


@rule("DCA-ONI-003")
def oni_003(p: Project) -> list[Finding]:
    return _metadata(p, p.classes_in("domain"), "domain type")


def _immutable(p: Project, klass: Klass) -> list[Finding]:
    found = [
        Finding(klass.module.where(f.line), f"{klass.name}.{f.name} is a mutable collection")
        for f in p.mutable_fields(klass)
    ]
    found += [
        Finding(klass.module.where(node), f"{klass.name}.{name} changes its state") for name, node in p.mutators(klass)
    ]
    return found


@rule("DCA-ADV-001")
def adv_001(p: Project) -> list[Finding]:
    found = [
        Finding(k.where(), f"{k.name} is named an event and does not extend DomainEvent")
        for k in p.classes_in("domain")
        if k.name.endswith("Event")
        and not k.is_protocol
        and not p.roles(k) & {"DomainEvent", "IntegrationEvent"}
        and not any(a.startswith("enum.") for a in p.ancestors(k))
    ]
    for event in p.with_role("DomainEvent"):
        found += _immutable(p, event)
    return found


@rule("DCA-ADV-002")
def adv_002(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the domain event {k.name} sits in {k.module.dotted}, outside the domain")
        for k in p.with_role("DomainEvent")
        if k.place.layer != "domain"
    ]


@rule("DCA-ADV-004")
def adv_004(p: Project) -> list[Finding]:
    return _metadata(p, in_domain(p, "DomainEvent"), "domain event")


@rule("DCA-ADV-005")
def adv_005(p: Project) -> list[Finding]:
    found = []
    for event in p.with_role("IntegrationEvent"):
        if not is_leaf(p, event):
            continue
        if not any(k.arg == "event_type" for k in event.node.keywords):
            found.append(
                Finding(
                    event.where(),
                    f"{event.name} names no event_type: class {event.name}("
                    "IntegrationEvent, event_type=..., version=...)",
                )
            )
    return found


def _version_fields(p: Project, classes: list[Klass]) -> list[Finding]:
    return [
        Finding(k.module.where(f.line), f"{k.name}.{f.name} carries a schema version in the payload")
        for k in classes
        for f in k.fields
        if f.name in VERSION_FIELDS
    ]


@rule("DCA-ADV-006")
def adv_006(p: Project) -> list[Finding]:
    return _version_fields(p, p.with_role("IntegrationEvent"))


@rule("DCA-ADV-007")
def adv_007(p: Project) -> list[Finding]:
    return _version_fields(p, [k for k in p.with_role("DomainEvent") if not p.has(k, "IntegrationEvent")])


@rule("DCA-ADV-008")
def adv_008(p: Project) -> list[Finding]:
    found = []
    wanted = set(p.layout.timestamp_types)
    for event in p.with_role("DomainEvent"):
        if not is_leaf(p, event):
            continue
        chain = [event, *[p.classes[a] for a in p.ancestors(event) if a in p.classes]]
        names = {n.rsplit(".", 1)[-1] for k in chain for f in k.fields for n in p.type_names(k.module, f.annotation)}
        if not names & wanted:
            found.append(Finding(event.where(), f"{event.name} holds no timestamp field ({', '.join(sorted(wanted))})"))
    return found


def _placed(p: Project, role: str, what: str) -> list[Finding]:
    return [
        Finding(k.where(), f"the {what} {k.name} sits in {k.module.dotted}, outside the domain")
        for k in p.with_role(role)
        if k.place.layer != "domain"
    ]


def _stateless(p: Project, role: str, what: str) -> list[Finding]:
    found = []
    for klass in p.with_role(role):
        found += [
            Finding(klass.module.where(node), f"the {what} {klass.name} keeps state: {name} assigns to self")
            for name, node in p.mutators(klass)
        ]
    return found


@rule("DCA-ADV-010")
def adv_010(p: Project) -> list[Finding]:
    return _placed(p, "DomainService", "domain service")


@rule("DCA-ADV-011")
def adv_011(p: Project) -> list[Finding]:
    return _metadata(p, in_domain(p, "DomainService"), "domain service")


@rule("DCA-ADV-012")
def adv_012(p: Project) -> list[Finding]:
    return _stateless(p, "DomainService", "domain service")


@rule("DCA-ADV-013")
def adv_013(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the factory {k.name} is not named *Factory")
        for k in p.with_role("Factory")
        if not k.name.endswith("Factory")
    ]


@rule("DCA-ADV-014")
def adv_014(p: Project) -> list[Finding]:
    return _placed(p, "Factory", "factory")


@rule("DCA-ADV-015")
def adv_015(p: Project) -> list[Finding]:
    return _metadata(p, in_domain(p, "Factory"), "factory")


@rule("DCA-ADV-016")
def adv_016(p: Project) -> list[Finding]:
    return _stateless(p, "Factory", "factory")


def specifications(p: Project) -> list[Klass]:
    return [k for k in p.classes.values() if p.has(k, "Specification") or k.name.endswith("Specification")]


@rule("DCA-ADV-017")
def adv_017(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the specification {k.name} sits in {k.module.dotted}, outside the domain")
        for k in specifications(p)
        if k.place.layer != "domain"
    ]


@rule("DCA-ADV-018")
def adv_018(p: Project) -> list[Finding]:
    return _metadata(p, [k for k in specifications(p) if k.place.layer == "domain"], "specification")


@rule("DCA-ADV-019")
def adv_019(p: Project) -> list[Finding]:
    found = []
    for klass in p.classes.values():
        if not p.roles(klass) & {"Entity", "Value"}:
            continue
        for method in klass.methods.values():
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func.value if isinstance(node.func, ast.Attribute) else node.func
                used = p.klass(klass.module, func)
                if used is not None and p.has(used, "DomainService"):
                    found.append(
                        Finding(
                            klass.module.where(node), f"{klass.name}.{method.name} uses the domain service {used.name}"
                        )
                    )
    return found


@rule("DCA-ADV-020")
def adv_020(p: Project) -> list[Finding]:
    found = []
    for service in p.with_role("DomainService"):
        for name, method in service.methods.items():
            if not public(name):
                continue
            takes = [n for a in parameters(method) for n in p.type_classes(service.module, a.annotation)]
            if not any(p.has(n, "Entity") for n in takes):
                found.append(
                    Finding(service.module.where(method), f"{service.name}.{name} takes no aggregate and no entity")
                )
    return found
