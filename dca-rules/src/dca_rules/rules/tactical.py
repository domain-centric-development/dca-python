"""Tactical rules: aggregates, entities, values, repositories and stores."""

from __future__ import annotations

import ast

from dca_rules.model import BB, Klass, Project, annotation_expr, is_dunder, parameters, public
from dca_rules.rules import Finding, rule

PRIMITIVES = frozenset(
    {
        "builtins.str",
        "builtins.int",
        "builtins.float",
        "builtins.bool",
        "builtins.bytes",
        "builtins.complex",
        "datetime.datetime",
        "datetime.date",
        "datetime.time",
        "datetime.timedelta",
        "uuid.UUID",
    }
)
TIME_PRIMITIVES = PRIMITIVES - {"builtins.bool"}


def is_leaf(p: Project, klass: Klass) -> bool:
    """No class of the project extends it: the concrete type, not an intermediate base."""
    return not any(klass.qualname in {p.canonical(b) for b in other.bases} for other in p.classes.values())


def field_types(p: Project, klass: Klass, role: str) -> list[tuple[str, int, Klass]]:
    """(field, line, the class it names) for every field whose type names a class with the role."""
    out = []
    for field in klass.fields:
        for named in p.type_classes(klass.module, field.annotation):
            if p.has(named, role) and (named is not klass or role == "AggregateRoot"):
                out.append((field.name, field.line, named))
    return out


def roots(p: Project) -> list[Klass]:
    return [k for k in p.with_role("AggregateRoot") if not k.is_protocol]


def entities(p: Project, *, roots_too: bool = True) -> list[Klass]:
    return [k for k in p.with_role("Entity") if not k.is_protocol and (roots_too or not p.has(k, "AggregateRoot"))]


def values(p: Project) -> list[Klass]:
    return [k for k in p.with_role("Value") if not k.is_protocol]


def setters(klass: Klass) -> list[tuple[str, ast.AST]]:
    """Public `set_<name>` methods with one parameter, and property setters."""
    out: list[tuple[str, ast.AST]] = []
    for name, method in klass.methods.items():
        if name.startswith("set_") and len(parameters(method)) == 1:
            out.append((name, method))
        for decorator in method.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "setter":
                out.append((f"{name} (property setter)", method))
    return out


@rule("DCA-TAC-001")
def tac_001(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"{k.name} is named an aggregate root and does not extend AggregateRoot")
        for k in p.classes_in("domain")
        if k.name.endswith("AggregateRoot") and not p.has(k, "AggregateRoot")
    ]


@rule("DCA-TAC-002")
def tac_002(p: Project) -> list[Finding]:
    found = []
    for root in roots(p):
        for name, line, named in field_types(p, root, "OutputPort"):
            found.append(Finding(root.module.where(line), f"{root.name}.{name} holds the output port {named.name}"))
        for field in root.fields:
            names = p.type_names(root.module, field.annotation)
            for name in names:
                if name.startswith(BB + ".") and name.rsplit(".", 1)[-1] in (
                    "OutputPort",
                    "Repository",
                    "Store",
                    "DomainEventPublisher",
                    "IntegrationEventPublisher",
                ):
                    found.append(Finding(root.module.where(field.line), f"{root.name}.{field.name} holds {name}"))
    return found


@rule("DCA-TAC-003")
def tac_003(p: Project) -> list[Finding]:
    return [
        Finding(
            r.module.where(line),
            f"{r.name}.{field} holds the aggregate root {named.name}; reference another aggregate by its id",
        )
        for r in roots(p)
        for field, line, named in field_types(p, r, "AggregateRoot")
    ]


@rule("DCA-TAC-004")
def tac_004(p: Project) -> list[Finding]:
    found = []
    for entity in entities(p):
        if not is_leaf(p, entity):
            continue
        chain = [entity, *[p.classes[a] for a in p.ancestors(entity) if a in p.classes]]
        if not any(p.has(n, "Id") for k in chain for f in k.fields for n in p.type_classes(k.module, f.annotation)):
            found.append(Finding(entity.where(), f"{entity.name} holds no field of an Id type; its identity is state"))
    return found


@rule("DCA-TAC-005")
def tac_005(p: Project) -> list[Finding]:
    found = []
    for module in p.modules.values():
        for call, klass in p.constructions(module):
            if not p.has(klass, "Entity") or p.has(klass, "AggregateRoot"):
                continue
            if module.place.layer == "domain" and module.place.owner == klass.place.owner:
                continue
            found.append(
                Finding(module.where(call), f"{module.dotted} builds the entity {klass.name}; only its aggregate does")
            )
    return found


@rule("DCA-TAC-006")
def tac_006(p: Project) -> list[Finding]:
    model = {k.qualname: k for k in entities(p) + values(p)}
    return [
        Finding(k.module.where(node), f"{k.name}.{name} is a setter; name the change in the domain's language")
        for k in model.values()
        for name, node in setters(k)
    ]


@rule("DCA-TAC-007")
def tac_007(p: Project) -> list[Finding]:
    return [
        Finding(e.module.where(line), f"{e.name}.{field} holds the aggregate root {named.name}")
        for e in entities(p, roots_too=False)
        for field, line, named in field_types(p, e, "AggregateRoot")
    ]


@rule("DCA-TAC-008")
def tac_008(p: Project) -> list[Finding]:
    return [
        Finding(v.module.where(line), f"{v.name}.{field} holds the entity {named.name}")
        for v in values(p)
        for field, line, named in field_types(p, v, "Entity")
    ]


@rule("DCA-TAC-009")
def tac_009(p: Project) -> list[Finding]:
    found = []
    for klass in p.classes.values():
        for base in p.base_classes(klass):
            if p.has(base, "Value") and base.place.layer is not None and base.fields:
                found.append(Finding(klass.where(), f"{klass.name} extends the value {base.name}; a value is final"))
    return found


@rule("DCA-TAC-010")
def tac_010(p: Project) -> list[Finding]:
    found = []
    for value in values(p):
        for field in p.mutable_fields(value):
            found.append(
                Finding(
                    value.module.where(field.line),
                    f"{value.name}.{field.name} is a mutable collection; use a tuple or a frozenset",
                )
            )
        for name, node in p.mutators(value):
            found.append(Finding(value.module.where(node), f"{value.name}.{name} changes the value's state"))
    return found


@rule("DCA-TAC-011")
def tac_011(p: Project) -> list[Finding]:
    return [
        Finding(v.module.where(node), f"{v.name}.{name} is a setter on a value")
        for v in values(p)
        for name, node in v.methods.items()
        if name.startswith("set_")
    ]


@rule("DCA-TAC-012")
def tac_012(p: Project) -> list[Finding]:
    found = []
    for value in values(p):
        if "__eq__" in value.methods:
            found.append(
                Finding(
                    value.module.where(value.methods["__eq__"]),
                    f"{value.name} replaces the attribute equality its base gives it",
                )
            )
        decorator = p.is_dataclass(value)
        if isinstance(decorator, ast.Call) and any(
            k.arg == "eq" and isinstance(k.value, ast.Constant) and k.value.value is False for k in decorator.keywords
        ):
            found.append(Finding(value.module.where(decorator), f"{value.name} turns attribute equality off"))
    return found


def port_protocols(p: Project, role: str) -> list[Klass]:
    return [k for k in p.with_role(role) if k.is_protocol]


def implementations(p: Project, role: str) -> list[Klass]:
    return [k for k in p.with_role(role) if not k.is_protocol]


@rule("DCA-TAC-013")
def tac_013(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"{k.name} is named a repository and does not extend Repository")
        for k in p.classes_in("application")
        if k.name.endswith("Repository") and not p.has(k, "Repository")
    ]


@rule("DCA-TAC-014")
def tac_014(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the repository port {k.name} sits in {k.module.dotted}, outside the application")
        for k in port_protocols(p, "Repository")
        if k.place.layer != "application"
    ]


@rule("DCA-TAC-015")
def tac_015(p: Project) -> list[Finding]:
    return [
        Finding(
            k.where(), f"the repository {k.name} is implemented in {k.module.dotted}, outside the outgoing adapters"
        )
        for k in implementations(p, "Repository")
        if k.place.layer != "outgoing"
    ]


def type_arguments(klass: Klass, role_base: str, p: Project) -> list[ast.expr]:
    """The type arguments of the base that gives a class a role: `Repository[Thing, ThingId]` gives Thing, ThingId."""
    for base in klass.node.bases:
        if isinstance(base, ast.Subscript):
            name = p.resolve(klass.module, base.value)
            if name and (name == role_base or (name in p.classes and p.has(p.classes[name], "Repository"))):
                inner = base.slice
                return list(inner.elts) if isinstance(inner, ast.Tuple) else [inner]
    return []


@rule("DCA-TAC-016")
def tac_016(p: Project) -> list[Finding]:
    found = []
    for port in port_protocols(p, "Repository"):
        arguments = type_arguments(port, f"{BB}.Repository", p)
        if not arguments:
            continue
        managed = p.klass(port.module, arguments[0])
        if managed is not None and not p.has(managed, "AggregateRoot"):
            found.append(Finding(port.where(), f"{port.name} manages {managed.name}, which is no aggregate root"))
        elif managed is not None and port.name != f"{managed.name}Repository":
            found.append(Finding(port.where(), f"{port.name} manages {managed.name}; name it {managed.name}Repository"))
    return found


@rule("DCA-TAC-017")
def tac_017(p: Project) -> list[Finding]:
    found = []
    for port in port_protocols(p, "Repository"):
        for name, method in port.methods.items():
            for named in p.type_classes(port.module, method.returns):
                if p.has(named, "Entity") and not p.has(named, "AggregateRoot"):
                    found.append(
                        Finding(
                            port.module.where(method),
                            f"{port.name}.{name} returns the entity {named.name}, which is no aggregate root",
                        )
                    )
    return found


@rule("DCA-TAC-018")
def tac_018(p: Project) -> list[Finding]:
    found = []
    for klass in p.classes.values():
        if not klass.name.endswith("Store") or klass.place.layer in ("outgoing", "infrastructure", "root", "adapter"):
            continue
        if not klass.is_protocol:
            continue
        if not p.has(klass, "Store") or p.has(klass, "Repository"):
            found.append(Finding(klass.where(), f"{klass.name} is named a store and does not extend Store alone"))
    return found


@rule("DCA-TAC-019")
def tac_019(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the store port {k.name} sits in {k.module.dotted}, outside the application")
        for k in port_protocols(p, "Store")
        if k.place.layer != "application"
    ]


@rule("DCA-TAC-020")
def tac_020(p: Project) -> list[Finding]:
    return [
        Finding(k.where(), f"the store {k.name} is implemented in {k.module.dotted}, outside the outgoing adapters")
        for k in implementations(p, "Store")
        if k.place.layer != "outgoing"
    ]


@rule("DCA-TAC-021")
def tac_021(p: Project) -> list[Finding]:
    return [
        Finding(k.module.where(k.methods[n]), f"the store {k.name} declares {n}")
        for k in port_protocols(p, "Store")
        for n in ("save", "delete", "delete_by_id")
        if n in k.methods
    ]


@rule("DCA-TAC-023")
def tac_023(p: Project) -> list[Finding]:
    found = []
    for module in p.modules.values():
        for call, klass in p.constructions(module):
            if p.has(klass, "AggregateRoot") and not klass.is_protocol and klass.module is not module:
                found.append(
                    Finding(
                        module.where(call),
                        f"{module.dotted} calls {klass.name}(...) itself; the root "
                        "is built through its own class methods",
                    )
                )
    return found


NEUTRAL = ("of", "new", "create", "value_of", "make")


@rule("DCA-TAC-024")
def tac_024(p: Project) -> list[Finding]:
    found = []
    for value in values(p):
        factories = {}
        for name, method in value.methods.items():
            if any(isinstance(d, ast.Name) and d.id == "classmethod" for d in method.decorator_list):
                factories[name] = tuple(ast.unparse(a.annotation) if a.annotation else "?" for a in parameters(method))
        for neutral in NEUTRAL:
            if neutral not in factories:
                continue
            for other, signature in factories.items():
                if other != neutral and signature == factories[neutral]:
                    found.append(
                        Finding(
                            value.module.where(value.methods[neutral]),
                            f"{value.name}.{neutral} takes what {other} takes; one origin, one name",
                        )
                    )
    return found


def _wrapper(p: Project, klass: Klass) -> bool:
    return bool(p.roles(klass) & {"Value", "Id"}) and len(klass.fields) == 1 and klass.fields[0].name == "value"


def _bare(p: Project, klass: Klass, annotation: ast.expr | None) -> list[str]:
    return sorted(
        {n.rsplit(".", 1)[-1] for n in p.type_names(klass.module, annotation_expr(annotation)) if n in PRIMITIVES}
    )


def _rebuilds(p: Project, klass: Klass, name: str, method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """The factory that rebuilds a stored object: a class or static method named as configured, returning the class."""
    factory = any(isinstance(d, ast.Name) and d.id in ("classmethod", "staticmethod") for d in method.decorator_list)
    returned = method.returns
    returns_class = returned is not None and (ast.unparse(returned).strip("'\"") in (klass.name, "Self", "typing.Self"))
    return factory and returns_class and name.lower() in {n.lower() for n in p.layout.reconstituting_factories}


@rule("DCA-TAC-025")
def tac_025(p: Project) -> list[Finding]:
    found = []
    for klass in p.classes_in("domain"):
        ancestors = p.ancestors(klass)
        if (
            _wrapper(p, klass)
            or "builtins.Exception" in ancestors
            or "builtins.BaseException" in ancestors
            or any(a.startswith("enum.") for a in ancestors)
            or p.has(klass, "DomainException")
        ):
            continue
        for field in klass.fields:
            bare = _bare(p, klass, field.annotation)
            if bare == ["bool"] and not field.public:
                continue
            if bare:
                found.append(
                    Finding(
                        klass.module.where(field.line),
                        f"{klass.name}.{field.name} is {', '.join(bare)}; wrap it in a value",
                    )
                )
        for name, method in klass.methods.items():
            if is_dunder(name) or not public(name):
                continue
            rebuilds = _rebuilds(p, klass, name, method)
            for argument in parameters(method):
                bare = _bare(p, klass, argument.annotation)
                if rebuilds and bare == ["bool"]:
                    continue
                if bare:
                    found.append(
                        Finding(
                            klass.module.where(argument), f"{klass.name}.{name}({argument.arg}) takes {', '.join(bare)}"
                        )
                    )
            bare = [b for b in _bare(p, klass, method.returns) if b != "bool"]
            if bare:
                found.append(Finding(klass.module.where(method), f"{klass.name}.{name} returns {', '.join(bare)}"))
    return found


def _owner(p: Project, root: Klass) -> tuple[bool, Klass | None]:
    """(marked Owned, the owner's id class) of an aggregate, through its bases."""
    for klass in [root, *[p.classes[a] for a in p.ancestors(root) if a in p.classes]]:
        for base in klass.node.bases:
            target = base.value if isinstance(base, ast.Subscript) else base
            if p.resolve(klass.module, target) != f"{BB}.Owned":
                continue
            if not isinstance(base, ast.Subscript):
                return True, None
            owner = p.klass(klass.module, base.slice)
            return True, owner if owner is not None and p.has(owner, "Id") else None
    return False, None


def _repository_methods(p: Project, port: Klass) -> list[tuple[Klass, ast.FunctionDef | ast.AsyncFunctionDef]]:
    out = [(port, m) for m in port.methods.values()]
    for base in p.base_classes(port):
        if base.is_protocol:
            out += _repository_methods(p, base)
    return out


@rule("DCA-TAC-026")
def tac_026(p: Project) -> list[Finding]:
    found = []
    for root in roots(p):
        owned, owner = _owner(p, root)
        if not owned:
            continue
        if owner is None:
            found.append(Finding(root.where(), f"{root.name} is Owned without the owner's id type: Owned[<OwnerId>]"))
            continue
        id_type = None
        id_property = next((m for k in [root, *p.base_classes(root)] for n, m in k.methods.items() if n == "id"), None)
        if id_property is not None:
            id_type = next(iter(p.type_classes(root.module, id_property.returns)), None)
        for port in port_protocols(p, "Repository"):
            arguments = type_arguments(port, f"{BB}.Repository", p)
            if not arguments or p.klass(port.module, arguments[0]) is not root:
                continue
            if len(arguments) > 1:
                id_type = p.klass(port.module, arguments[1]) or id_type
            scoped = False
            for home, method in _repository_methods(p, port):
                takes = [set(n.qualname for n in p.type_classes(home.module, a.annotation)) for a in parameters(method)]
                returns = {n.qualname for n in p.type_classes(home.module, method.returns)}
                by_id = any(
                    (id_type is not None and id_type.qualname in t)
                    or any(p.has(p.classes[q], "Id") and q != owner.qualname for q in t)
                    for t in takes
                )
                by_owner = any(owner.qualname in t for t in takes)
                if by_id and by_owner and root.qualname in returns:
                    scoped = True
            if not scoped:
                found.append(
                    Finding(
                        port.where(),
                        f"{port.name} offers no lookup of {root.name} by its id and the owner's {owner.name}",
                    )
                )
    return found
