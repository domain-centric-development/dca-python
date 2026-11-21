"""Tactical rules: aggregates, entities, values, repositories and stores."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from dca_rules.model import BB, Klass, Module, Project, annotation_expr, functions, is_dunder, parameters, public
from dca_rules.rules import Checked, Finding, rule

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
        "uuid.UUID",
    }
)
TIME_PRIMITIVES = PRIMITIVES - {"builtins.bool"}


def is_leaf(p: Project, klass: Klass) -> bool:
    """No class of the project extends it: the concrete type, not an intermediate base."""
    return not any(klass.qualname in {p.canonical(b) for b in other.bases} for other in p.classes.values())


def field_types(p: Project, klass: Klass, role: str) -> list[tuple[str, str, Klass]]:
    """(field, where, the class it names) for every field whose type names a class with the role, the fields of
    role-less bases included."""
    out = []
    for field in p.member_fields(klass):
        for named in p.type_classes(field.module, field.annotation):
            if p.has(named, role) and (named is not klass or role == "AggregateRoot"):
                out.append((field.name, field.module.where(field.line), named))
    return out


def roots(p: Project) -> list[Klass]:
    return [k for k in p.with_role("AggregateRoot") if not k.is_protocol]


def entities(p: Project, *, roots_too: bool = True) -> list[Klass]:
    return [k for k in p.with_role("Entity") if not k.is_protocol and (roots_too or not p.has(k, "AggregateRoot"))]


def values(p: Project) -> list[Klass]:
    return [k for k in p.with_role("Value") if not k.is_protocol]


def _fluent(method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A method that returns its own object (`return self`) or another one of its class: a fluent builder step or a
    copy with one value changed, no setter."""
    if any(
        isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == "self" for n in ast.walk(method)
    ):
        return True
    returned = ast.unparse(method.returns).strip("'\"") if method.returns is not None else ""
    return returned in ("Self", "typing.Self")


def setters(p: Project, klass: Klass) -> list[tuple[str, ast.AST, Module]]:
    """Public `set_<name>` methods with one parameter that return nothing of their class, and property setters; the
    methods of role-less bases included."""
    out: list[tuple[str, ast.AST, Module]] = []
    for owner, name, method in p.member_methods(klass):
        if name.startswith("set_") and len(parameters(method)) == 1 and not _fluent(method):
            out.append((name, method, owner.module))
        for decorator in method.decorator_list:
            if isinstance(decorator, ast.Attribute) and decorator.attr == "setter":
                out.append((f"{name} (property setter)", method, owner.module))
    return out


@rule("DCA-TAC-001")
def tac_001(p: Project) -> Checked:
    suffix = p.layout.aggregate_root_suffix
    selected = [k for k in p.classes_in("domain") if k.name.endswith(suffix) or p.has(k, "AggregateRoot")]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} is named an aggregate root and does not extend AggregateRoot")
            for k in selected
            if not p.has(k, "AggregateRoot")
        ],
    )


@rule("DCA-TAC-002")
def tac_002(p: Project) -> Checked:
    found = []
    selected = roots(p)
    for root in selected:
        for name, where, named in field_types(p, root, "OutputPort"):
            found.append(Finding(where, f"{root.name}.{name} holds the output port {named.name}"))
        for field in p.member_fields(root):
            names = p.type_names(field.module, field.annotation)
            for name in names:
                if name.startswith(BB + ".") and name.rsplit(".", 1)[-1] in (
                    "OutputPort",
                    "Repository",
                    "Store",
                    "DomainEventPublisher",
                    "IntegrationEventPublisher",
                ):
                    found.append(Finding(field.module.where(field.line), f"{root.name}.{field.name} holds {name}"))
    return Checked(len(selected), found)


@rule("DCA-TAC-003")
def tac_003(p: Project) -> Checked:
    selected = roots(p)
    return Checked(
        len(selected),
        [
            Finding(
                where,
                f"{r.name}.{field} holds the aggregate root {named.name}; reference another aggregate by its id",
            )
            for r in selected
            for field, where, named in field_types(p, r, "AggregateRoot")
        ],
    )


@rule("DCA-TAC-004")
def tac_004(p: Project) -> Checked:
    found = []
    selected = [e for e in entities(p) if is_leaf(p, e)]
    for entity in selected:
        chain = [entity, *[p.classes[a] for a in p.ancestors(entity) if a in p.classes]]
        if not any(p.has(n, "Id") for k in chain for f in k.fields for n in p.type_classes(k.module, f.annotation)):
            found.append(Finding(entity.where(), f"{entity.name} holds no field of an Id type; its identity is state"))
    return Checked(len(selected), found)


REPLACE = ("dataclasses.replace", "copy.replace")


def builds(p: Project, module: Module) -> Iterator[tuple[ast.Call, Klass]]:
    """Every construction of a project class in a module: a call of the class, and a `dataclasses.replace(x, ...)`
    (or `copy.replace`) of an `x` typed with one - a parameter or local annotated so, or `self` in its methods."""
    yield from p.constructions(module)
    owners = {id(m): k for k in p.classes.values() if k.module is module for m in k.methods.values()}
    seen: set[int] = set()
    for scope in functions(module.tree):
        typed: dict[str, list[Klass]] = {a.arg: p.type_classes(module, a.annotation) for a in parameters(scope)}
        if id(scope) in owners:
            typed["self"] = [owners[id(scope)]]
        for node in ast.walk(scope):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                typed[node.target.id] = p.type_classes(module, node.annotation)
        for node in ast.walk(scope):
            if (
                isinstance(node, ast.Call)
                and id(node) not in seen
                and node.args
                and isinstance(node.args[0], ast.Name)
                and p.resolve(module, node.func) in REPLACE
            ):
                seen.add(id(node))
                for klass in typed.get(node.args[0].id, []):
                    yield node, klass


@rule("DCA-TAC-005")
def tac_005(p: Project) -> Checked:
    """Selects the entities that are no aggregate root, and checks every place that builds one: the entity itself or
    an aggregate root, entity or factory in the domain of the entity's own context."""
    found = []
    # The innermost class around each node: nested classes are classes of their own.
    enclosing: dict[int, Klass] = {}
    for klass in sorted(p.classes.values(), key=lambda k: -k.qualname.count(".")):
        for node in ast.walk(klass.node):
            enclosing.setdefault(id(node), klass)
    for module in p.modules.values():
        for call, klass in builds(p, module):
            if not p.has(klass, "Entity") or p.has(klass, "AggregateRoot"):
                continue
            builder = enclosing.get(id(call))
            if (
                builder is not None
                and builder.place.layer == "domain"
                and p.roles(builder) & {"AggregateRoot", "Entity", "Factory"}
                and builder.place.owner == klass.place.owner
            ):
                continue
            found.append(
                Finding(
                    module.where(call),
                    f"{module.dotted} builds the entity {klass.name}; only its aggregate, an entity or a factory "
                    "of its context's domain does",
                )
            )
    return Checked(len(entities(p, roots_too=False)), found)


@rule("DCA-TAC-006")
def tac_006(p: Project) -> Checked:
    model = {k.qualname: k for k in entities(p) + values(p)}
    return Checked(
        len(model),
        [
            Finding(home.where(node), f"{k.name}.{name} is a setter; name the change in the domain's language")
            for k in model.values()
            for name, node, home in setters(p, k)
        ],
    )


@rule("DCA-TAC-007")
def tac_007(p: Project) -> Checked:
    selected = entities(p, roots_too=False)
    return Checked(
        len(selected),
        [
            Finding(where, f"{e.name}.{field} holds the aggregate root {named.name}")
            for e in selected
            for field, where, named in field_types(p, e, "AggregateRoot")
        ],
    )


@rule("DCA-TAC-008")
def tac_008(p: Project) -> Checked:
    selected = values(p)
    return Checked(
        len(selected),
        [
            Finding(where, f"{v.name}.{field} holds the entity {named.name}")
            for v in selected
            for field, where, named in field_types(p, v, "Entity")
        ],
    )


@rule("DCA-TAC-009")
def tac_009(p: Project) -> Checked:
    """Selects the values, and checks every class for one it extends."""
    found = []
    for klass in p.classes.values():
        for base in p.base_classes(klass):
            if p.has(base, "Value") and base.place.layer is not None and base.fields:
                found.append(Finding(klass.where(), f"{klass.name} extends the value {base.name}; a value is final"))
    return Checked(len(values(p)), found)


@rule("DCA-TAC-010")
def tac_010(p: Project) -> Checked:
    found = []
    selected = values(p)
    for value in selected:
        for field in p.mutable_fields(value):
            found.append(
                Finding(
                    field.module.where(field.line),
                    f"{value.name}.{field.name} is a mutable collection; use a tuple or a frozenset",
                )
            )
        for name, node, home in p.mutators(value):
            found.append(Finding(home.where(node), f"{value.name}.{name} changes the value's state"))
    return Checked(len(selected), found)


@rule("DCA-TAC-011")
def tac_011(p: Project) -> Checked:
    selected = values(p)
    return Checked(
        len(selected),
        [
            Finding(owner.module.where(node), f"{v.name}.{name} is a setter on a value")
            for v in selected
            for owner, name, node in p.member_methods(v)
            if name.startswith("set_")
        ],
    )


@rule("DCA-TAC-012")
def tac_012(p: Project) -> Checked:
    found = []
    selected = values(p)
    for value in selected:
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
    return Checked(len(selected), found)


def port_protocols(p: Project, role: str) -> list[Klass]:
    return [k for k in p.with_role(role) if k.is_protocol]


def implementations(p: Project, role: str) -> list[Klass]:
    return [k for k in p.with_role(role) if not k.is_protocol]


@rule("DCA-TAC-013")
def tac_013(p: Project) -> Checked:
    suffix = p.layout.repository_suffix
    selected = [k for k in p.classes_in("application") if k.name.endswith(suffix) or p.has(k, "Repository")]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} is named a repository and does not extend Repository")
            for k in selected
            if not p.has(k, "Repository")
        ],
    )


@rule("DCA-TAC-014")
def tac_014(p: Project) -> Checked:
    selected = port_protocols(p, "Repository")
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the repository port {k.name} sits in {k.module.dotted}, outside the application")
            for k in selected
            if k.place.layer != "application"
        ],
    )


@rule("DCA-TAC-015")
def tac_015(p: Project) -> Checked:
    selected = implementations(p, "Repository")
    return Checked(
        len(selected),
        [
            Finding(
                k.where(),
                f"the repository {k.name} is implemented in {k.module.dotted}, outside the outgoing adapters",
            )
            for k in selected
            if k.place.layer != "outgoing"
        ],
    )


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
def tac_016(p: Project) -> Checked:
    found = []
    selected = port_protocols(p, "Repository")
    for port in selected:
        arguments = type_arguments(port, f"{BB}.Repository", p)
        if not arguments:
            continue
        managed = p.klass(port.module, arguments[0])
        if managed is not None and not p.has(managed, "AggregateRoot"):
            found.append(Finding(port.where(), f"{port.name} manages {managed.name}, which is no aggregate root"))
        elif managed is not None and port.name != f"{managed.name}{p.layout.repository_suffix}":
            expected = f"{managed.name}{p.layout.repository_suffix}"
            found.append(Finding(port.where(), f"{port.name} manages {managed.name}; name it {expected}"))
    return Checked(len(selected), found)


@rule("DCA-TAC-017")
def tac_017(p: Project) -> Checked:
    found = []
    selected = port_protocols(p, "Repository")
    for port in selected:
        for name, method in port.methods.items():
            for named in p.type_classes(port.module, method.returns):
                if p.has(named, "Entity") and not p.has(named, "AggregateRoot"):
                    found.append(
                        Finding(
                            port.module.where(method),
                            f"{port.name}.{name} returns the entity {named.name}, which is no aggregate root",
                        )
                    )
    return Checked(len(selected), found)


@rule("DCA-TAC-018")
def tac_018(p: Project) -> Checked:
    found = []
    selected = [
        k
        for k in p.classes.values()
        if k.is_protocol
        and (k.name.endswith(p.layout.store_suffix) or p.has(k, "Store"))
        and k.place.layer not in ("incoming", "outgoing", "infrastructure", "root", "adapter")
    ]
    for klass in selected:
        if klass.name.endswith(p.layout.store_suffix) and (not p.has(klass, "Store") or p.has(klass, "Repository")):
            found.append(Finding(klass.where(), f"{klass.name} is named a store and does not extend Store alone"))
    return Checked(len(selected), found)


@rule("DCA-TAC-019")
def tac_019(p: Project) -> Checked:
    selected = port_protocols(p, "Store")
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the store port {k.name} sits in {k.module.dotted}, outside the application")
            for k in selected
            if k.place.layer != "application"
        ],
    )


@rule("DCA-TAC-020")
def tac_020(p: Project) -> Checked:
    selected = implementations(p, "Store")
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the store {k.name} is implemented in {k.module.dotted}, outside the outgoing adapters")
            for k in selected
            if k.place.layer != "outgoing"
        ],
    )


@rule("DCA-TAC-021")
def tac_021(p: Project) -> Checked:
    selected = port_protocols(p, "Store")
    return Checked(
        len(selected),
        [
            Finding(k.module.where(k.methods[n]), f"the store {k.name} declares {n}")
            for k in selected
            for n in ("save", "delete", "delete_by_id")
            if n in k.methods
        ],
    )


@rule("DCA-TAC-023")
def tac_023(p: Project) -> Checked:
    """Selects the aggregate roots, and checks every place that builds one."""
    found = []
    for module in p.modules.values():
        for call, klass in builds(p, module):
            if p.has(klass, "AggregateRoot") and not klass.is_protocol and klass.module is not module:
                found.append(
                    Finding(
                        module.where(call),
                        f"{module.dotted} calls {klass.name}(...) itself; the root "
                        "is built through its own class methods",
                    )
                )
    return Checked(len(roots(p)), found)


NEUTRAL = ("of", "new", "create", "value_of", "make")


@rule("DCA-TAC-024")
def tac_024(p: Project) -> Checked:
    found = []
    selected = values(p)
    for value in selected:
        factories = {}
        for name, method in value.methods.items():
            if public(name) and builds_class(value, method):
                factories[name] = tuple(
                    tuple(p.type_names(value.module, annotation_expr(a.annotation))) or ("?",)
                    for a in parameters(method)
                )
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
    return Checked(len(selected), found)


def _wrapper(p: Project, klass: Klass) -> bool:
    """A value or an id with exactly one field, whatever its name: the wrapper of a bare value."""
    return bool(p.roles(klass) & {"Value", "Id"}) and len(p.member_fields(klass)) == 1


def _bare(p: Project, klass: Klass, annotation: ast.expr | None) -> list[str]:
    return sorted(
        {n.rsplit(".", 1)[-1] for n in p.type_names(klass.module, annotation_expr(annotation)) if n in PRIMITIVES}
    )


def builds_class(klass: Klass, method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A class or static method annotated to return its class (or Self): a constructor by another name."""
    factory = any(isinstance(d, ast.Name) and d.id in ("classmethod", "staticmethod") for d in method.decorator_list)
    returned = method.returns
    return (
        factory and returned is not None and ast.unparse(returned).strip("'\"") in (klass.name, "Self", "typing.Self")
    )


def _rebuilds(p: Project, klass: Klass, name: str, method: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """The factory that rebuilds a stored object: a class or static method named as configured, returning the class."""
    return builds_class(klass, method) and name.lower() in {n.lower() for n in p.layout.reconstituting_factories}


OPPOSITES = {
    frozenset(pair)
    for pair in (("yes", "no"), ("true", "false"), ("on", "off"), ("present", "absent"), ("enabled", "disabled"))
}


def _members(klass: Klass) -> list[str]:
    """The names an enum class assigns in its body, private ones left out."""
    names = []
    for statement in klass.node.body:
        targets = statement.targets if isinstance(statement, ast.Assign) else []
        if isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets = [statement.target]
        names += [t.id for t in targets if isinstance(t, ast.Name) and not t.id.startswith("_")]
    return names


#: The endings of an adjective-like state, which `un` negates (LOCKED/UNLOCKED); an action it does not (LOCK/UNLOCK).
ADJECTIVE_ENDINGS = ("ed", "able", "ible", "ive", "ent", "ant", "al", "ful")


def yes_no(names: list[str]) -> bool:
    """Two names that are one fact and its negation: a known pair, X beside NOT_X, NO_X or NON_X, or an
    adjective-like X beside UN_X."""
    if len(names) != 2:
        return False
    a, b = (n.lower().replace("_", "") for n in names)
    if frozenset((a, b)) in OPPOSITES:
        return True
    for shorter, longer in ((a, b), (b, a)):
        if any(longer == prefix + shorter for prefix in ("not", "no", "non")):
            return True
        if longer == "un" + shorter and shorter.endswith(ADJECTIVE_ENDINGS):
            return True
    return False


@rule("DCA-TAC-025")
def tac_025(p: Project) -> Checked:
    found = []
    selected = p.classes_in("domain")
    for klass in selected:
        ancestors = p.ancestors(klass)
        enum = any(a.startswith("enum.") for a in ancestors)
        if enum and yes_no(_members(klass)):
            found.append(
                Finding(
                    klass.where(),
                    f"{klass.name} names one fact and its negation ({', '.join(_members(klass))}); a boolean in "
                    "disguise - a bool field, two methods, or cases with names of their own",
                )
            )
        if (
            _wrapper(p, klass)
            or "builtins.Exception" in ancestors
            or "builtins.BaseException" in ancestors
            or p.has(klass, "DomainException")
        ):
            continue
        # An enum's members are its cases, no fields; its methods are read like any other.
        for field in [] if enum else klass.fields:
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
            if is_dunder(name):
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
    return Checked(len(selected), found)


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
def tac_026(p: Project) -> Checked:
    found = []
    selected = [(root, owner) for root in roots(p) for owned, owner in [_owner(p, root)] if owned]
    for root, owner in selected:
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
    return Checked(len(selected), found)


MODEL_ROLES = ("AggregateRoot", "Entity", "Value", "Factory", "Specification")


def _is_gateway(p: Project, name: str) -> bool:
    if name == f"{BB}.DomainGateway":
        return True
    klass = p.classes.get(name)
    return klass is not None and p.has(klass, "DomainGateway")


def _names_gateway(p: Project, module: Module, annotation: ast.expr | None) -> str | None:
    """The gateway an annotation names, through generic arguments."""
    for name in p.type_names(module, annotation):
        if _is_gateway(p, name):
            return name.rsplit(".", 1)[-1]
    return None


def _looked_up(p: Project, name: str) -> str | None:
    """The gateway a qualified name hands out without a parameter: a module variable annotated with one or bound to
    a built implementation, a class attribute annotated with one, a function or a method that returns one. An
    attribute chain is read from each of its prefixes."""
    parts = name.split(".")
    for end in range(len(parts), 1, -1):
        owner, attr = ".".join(parts[: end - 1]), parts[end - 1]
        module = p.modules.get(owner)
        if module is not None:
            node = module.defined.get(attr)
            if isinstance(node, ast.AnnAssign):
                return _names_gateway(p, module, node.annotation)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                built = p.klass(module, node.value.func)
                return built.name if built is not None and p.has(built, "DomainGateway") else None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return _names_gateway(p, module, node.returns)
            continue
        klass = p.classes.get(owner)
        if klass is not None:
            method = klass.methods.get(attr)
            if method is not None:
                return _names_gateway(p, klass.module, method.returns)
            for field in klass.fields:
                if field.name == attr:
                    return _names_gateway(p, klass.module, field.annotation)
    return None


@rule("DCA-TAC-027")
def tac_027(p: Project) -> Checked:
    """Selects the aggregates, entities, values, factories and specifications that are no gateway themselves. A
    gateway taken as a parameter and called passes; held, returned, looked up or built, it does not."""
    selected = [
        k
        for k in p.classes.values()
        if not k.is_protocol
        and not p.has(k, "DomainGateway")
        and (p.roles(k) & set(MODEL_ROLES) or k.name.endswith(p.layout.specification_suffix))
    ]
    found: dict[tuple[str, int], str] = {}

    def report(klass: Klass, line: int, what: str) -> None:
        found.setdefault((klass.module.path, line), f"{klass.name} {what}; take the gateway as a parameter")

    for klass in selected:
        module = klass.module
        for field in klass.fields:
            gateway = _names_gateway(p, module, field.annotation)
            if gateway:
                report(klass, field.line, f"holds the domain gateway {gateway} in {field.name}")
        for statement in klass.node.body:
            if isinstance(statement, ast.Assign):
                for _, name in p.refs(module, statement.value):
                    gateway = _looked_up(p, name)
                    if gateway:
                        report(klass, statement.lineno, f"holds the domain gateway {gateway} in a class attribute")
        for method in klass.methods.values():
            gateway = _names_gateway(p, module, method.returns)
            if gateway:
                report(klass, method.lineno, f"{method.name} returns the domain gateway {gateway}")
            given = {a.arg for a in parameters(method) if _names_gateway(p, module, a.annotation)}
            for item in ast.walk(method):
                if isinstance(item, ast.Assign) and isinstance(item.value, ast.Name) and item.value.id in given:
                    for target in item.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            report(klass, item.lineno, f"keeps the domain gateway {item.value.id} in {target.attr}")
            for node, name in p.refs(module, ast.Module(body=method.body, type_ignores=[])):
                gateway = _looked_up(p, name)
                if gateway:
                    report(klass, node.lineno, f"looks up the domain gateway {gateway} through {name}")
            for call, built in p.constructions(module, method):
                if p.has(built, "DomainGateway") and not built.is_protocol:
                    report(klass, call.lineno, f"builds the domain gateway implementation {built.name}")
    return Checked(len(selected), [Finding(f"{path}:{line}", m) for (path, line), m in sorted(found.items())])
