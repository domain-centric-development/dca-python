"""Domain events, integration events, domain services, factories, specifications, and the framework metadata the
domain must not carry."""

from __future__ import annotations

import ast

from dca_rules.model import Klass, Module, Project, parameters, public
from dca_rules.rules import Finding, rule
from dca_rules.rules.tactical import builds_class, is_leaf

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


class _ServiceUses:
    """The uses of a domain service in one scope: (node, what, whether it constructs one)."""

    def __init__(self, p: Project, module: Module, names: set[str], attributes: set[str]) -> None:
        self.p = p
        self.module = module
        self.names = set(names)
        self.attributes = attributes
        self.found: list[tuple[ast.AST, str, bool]] = []

    def service(self, node: ast.expr) -> Klass | None:
        klass = self.p.klass(self.module, node)
        return klass if klass is not None and self.p.has(klass, "DomainService") else None

    def built(self, node: ast.expr) -> Klass | None:
        """The service an expression constructs: `Service(...)` or `Service.create(...)` returning the class."""
        if not isinstance(node, ast.Call):
            return None
        klass = self.service(node.func)
        if klass is not None:
            return klass
        if isinstance(node.func, ast.Attribute):
            owner = self.service(node.func.value)
            method = owner.methods.get(node.func.attr) if owner is not None else None
            if owner is not None and method is not None and builds_class(owner, method):
                return owner
        return None

    def holds(self, node: ast.expr) -> str | None:
        """What a receiver is when it holds a domain service: a name, `self.<attribute>`, or one built in place."""
        if isinstance(node, ast.Name) and node.id in self.names:
            return node.id
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr in self.attributes
        ):
            return f"self.{node.attr}"
        klass = self.built(node)
        return klass.name if klass is not None else None

    def bind(self, statement: ast.stmt) -> None:
        """A local binding that holds a domain service: annotated with one, or assigned a construction."""
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            typed = any(self.p.has(k, "DomainService") for k in self.p.type_classes(self.module, statement.annotation))
            if typed or (statement.value is not None and self.built(statement.value) is not None):
                self.names.add(statement.target.id)
        elif isinstance(statement, ast.Assign) and self.built(statement.value) is not None:
            self.names.update(t.id for t in statement.targets if isinstance(t, ast.Name))

    def read(self, nodes: list[ast.stmt]) -> None:
        for statement in nodes:
            for node in ast.walk(statement):
                if isinstance(node, ast.stmt):
                    self.bind(node)
                if not isinstance(node, ast.Call):
                    continue
                klass = self.service(node.func)
                if klass is not None:
                    self.found.append((node, f"constructs {klass.name}", True))
                    continue
                if not isinstance(node.func, ast.Attribute):
                    continue
                owner = self.service(node.func.value)
                if owner is not None:
                    method = owner.methods.get(node.func.attr)
                    constructs = method is not None and builds_class(owner, method)
                    verb = "constructs" if constructs else "calls"
                    self.found.append((node, f"{verb} {owner.name}.{node.func.attr}", constructs))
                    continue
                receiver = self.holds(node.func.value)
                if receiver is not None:
                    self.found.append((node, f"calls {receiver}.{node.func.attr}", False))


def _service_names(p: Project, module: Module, arguments: list[ast.arg]) -> set[str]:
    return {a.arg for a in arguments if any(p.has(k, "DomainService") for k in p.type_classes(module, a.annotation))}


def _service_attributes(p: Project, klass: Klass) -> set[str]:
    """`self.<attribute>`s that hold a domain service: typed with one, or assigned a construction."""
    typed = {name for name, roles in p.self_types(klass).items() if "DomainService" in roles}
    probe = _ServiceUses(p, klass.module, set(), set())
    for node in ast.walk(klass.node):
        if (
            isinstance(node, ast.Assign)
            and probe.built(node.value) is not None
            and any(
                isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
                for t in node.targets
            )
        ):
            typed.update(t.attr for t in node.targets if isinstance(t, ast.Attribute))
    return typed


@rule("DCA-ADV-021")
def adv_021(p: Project) -> list[Finding]:
    found = []
    for module in p.modules.values():
        layer = module.place.layer
        if layer == "application" or p.is_bb(module.dotted):
            continue
        root = layer in ("root", "infrastructure")
        classes = {k.node: k for k in p.classes.values() if k.module is module}
        top = _ServiceUses(p, module, set(), set())
        top.read(
            [s for s in module.tree.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        )
        scopes: list[tuple[str, _ServiceUses]] = [(module.dotted, top)]
        for statement in module.tree.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                uses = _ServiceUses(p, module, top.names | _service_names(p, module, parameters(statement)), set())
                uses.read(statement.body)
                scopes.append((statement.name, uses))
            elif isinstance(statement, ast.ClassDef):
                klass = classes.get(statement)
                if klass is None or p.has(klass, "DomainService"):
                    continue
                attributes = _service_attributes(p, klass)
                for name, method in klass.methods.items():
                    names = top.names | _service_names(p, module, parameters(method))
                    uses = _ServiceUses(p, module, names, attributes)
                    uses.read(method.body)
                    scopes.append((f"{klass.name}.{name}", uses))
        for where, uses in scopes:
            for node, what, construction in uses.found:
                if root and construction:
                    continue
                found.append(
                    Finding(
                        module.where(node),
                        f"{where} {what}; a domain service is used by the application and by other domain "
                        "services only",
                    )
                )
    return found
