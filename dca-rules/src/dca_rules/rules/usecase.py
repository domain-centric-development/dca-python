"""Use-case rules: commands, queries, results, the use case's shape and what it may call."""

from __future__ import annotations

import ast
from collections.abc import Callable

from dca_rules.model import BB, Klass, Module, Project, dotted_name, parameters, public
from dca_rules.rules import Checked, Finding, rule
from dca_rules.rules.hexagonal import is_use_case

#: Verbs that write, as a method name or its first word (`save`, `save_all`, `upsert_many`).
WRITES = (
    "save",
    "delete",
    "remove",
    "add",
    "insert",
    "update",
    "upsert",
    "put",
    "store",
    "write",
    "create",
    "append",
    "archive",
    "purge",
    "clear",
    "set",
    "mark",
)
PUBLISHES = ("publish", "publish_and_clear_events")


def use_cases(p: Project) -> list[Klass]:
    return [k for k in p.classes.values() if is_use_case(p, k)]


def suffixed(p: Project, suffix: str) -> list[Klass]:
    return [k for k in p.classes.values() if k.name.endswith(suffix)]


@rule("DCA-USE-001")
def use_001(p: Project) -> Checked:
    """Selects the input ports and every class named InputPort."""
    selected = [k for k in p.classes.values() if k.name == "InputPort" or (k.is_protocol and p.has(k, "InputPort"))]
    return Checked(
        len(selected),
        [
            Finding(k.where(), "the project declares its own InputPort; extend the building block's")
            for k in selected
            if k.name == "InputPort"
        ],
    )


def _placed(p: Project, suffix: str, layers: tuple[str, ...], where: str, values_too: bool = True) -> Checked:
    """Classes named with a suffix, placed in the layers; a value named so is selected unless `values_too` is off
    (a result may be a domain value)."""
    selected = [k for k in suffixed(p, suffix) if values_too or not p.has(k, "Value")]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} sits in {k.module.dotted}, outside {where}")
            for k in selected
            if k.place.layer not in layers
        ],
    )


@rule("DCA-USE-002")
def use_002(p: Project) -> Checked:
    return _placed(p, "Command", ("application",), "the application")


@rule("DCA-USE-003")
def use_003(p: Project) -> Checked:
    return _placed(p, "Query", ("application",), "the application")


def _immutable(p: Project, suffix: str) -> Checked:
    found = []
    selected = [k for k in suffixed(p, suffix) if k.place.layer == "application" and not k.is_protocol]
    for klass in selected:
        if not p.is_immutable_shape(klass):
            found.append(Finding(klass.where(), f"{klass.name} is no frozen dataclass, NamedTuple or enum"))
        found += [
            Finding(f.module.where(f.line), f"{klass.name}.{f.name} is a mutable collection")
            for f in p.mutable_fields(klass)
        ]
    return Checked(len(selected), found)


@rule("DCA-USE-004")
def use_004(p: Project) -> Checked:
    return _immutable(p, "Command")


@rule("DCA-USE-005")
def use_005(p: Project) -> Checked:
    return _immutable(p, "Query")


@rule("DCA-USE-006")
def use_006(p: Project) -> Checked:
    return _placed(p, "Result", ("application",), "the application", values_too=False)


@rule("DCA-USE-007")
def use_007(p: Project) -> Checked:
    return _immutable(p, "Result")


@rule("DCA-USE-008")
def use_008(p: Project) -> Checked:
    return _placed(p, "Response", ("incoming", "outgoing", "adapter"), "the adapters")


def receiver_calls(
    p: Project, klass: Klass, roles: set[str], accept: Callable[[str], bool]
) -> list[tuple[ast.Call, Module, str]]:
    """(call, its module, the method it sits in) for every call whose name `accept`s on a receiver that holds one of
    the roles - `self.<attr>`, a typed parameter or local, an alias - in the methods of the class and its role-less
    bases."""
    return [
        (call, owner.module, name)
        for owner, name, method in p.member_methods(klass)
        for call, called, held in p.calls(klass, method)
        if accept(called) and held & roles
    ]


def _own_references(p: Project, klass: Klass, node: ast.AST) -> set[str]:
    """The methods of the class (and its role-less bases) a piece of code names on `self`: called or handed on."""
    names = {name for _, name, _ in p.member_methods(klass)}
    return {
        n.attr
        for n in ast.walk(node)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self" and n.attr in names
    }


def reaches(p: Project, klass: Klass, hits: set[str]) -> set[str]:
    """The methods that run one of `hits` themselves or through the methods of their own they name, transitively."""
    methods = {name: method for _, name, method in p.member_methods(klass)}
    out = set(hits)
    changed = True
    while changed:
        changed = False
        for name, method in methods.items():
            if name not in out and _own_references(p, klass, method) & out:
                out.add(name)
                changed = True
    return out


def entry_points(p: Project, klass: Klass) -> list[tuple[Klass, str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    return [(o, n, m) for o, n, m in p.member_methods(klass) if public(n) or n == "__call__"]


@rule("DCA-USE-009")
def use_009(p: Project) -> Checked:
    """Selects the use cases; each entry point that saves an aggregate - itself or through its own methods - also
    calls publish_and_clear_events."""
    found = []
    selected = use_cases(p)
    for use_case in selected:
        saves = receiver_calls(p, use_case, {"Repository"}, lambda n: n == "save")
        publishes = receiver_calls(p, use_case, {"DomainEventPublisher"}, lambda n: n == "publish_and_clear_events")
        saving = reaches(p, use_case, {m for _, _, m in saves})
        publishing = reaches(p, use_case, {m for _, _, m in publishes})
        for owner, name, method in entry_points(p, use_case):
            if name in saving and name not in publishing:
                found.append(
                    Finding(
                        owner.module.where(method),
                        f"{use_case.name}.{name} saves an aggregate and never calls publish_and_clear_events",
                    )
                )
    return Checked(len(selected), found)


def _dto(p: Project, layer: str) -> Checked:
    found = []
    selected = p.in_layer(layer)
    for module in selected:
        for statement in module.tree.body:
            if isinstance(statement, ast.ClassDef) and statement.name.lower().endswith("dto"):
                found.append(Finding(module.where(statement), f"{module.dotted} declares the DTO {statement.name}"))
        seen = set()
        for node, name in p.refs(module, module.tree):
            short = name.rsplit(".", 1)[-1]
            if (
                short.lower().endswith("dto")
                and short[:1].isupper()
                and name not in seen
                and not name.startswith(module.dotted + ".")
            ):
                seen.add(name)
                found.append(Finding(module.where(node), f"{module.dotted} names the DTO {short}"))
    return Checked(len(selected), found)


@rule("DCA-USE-010")
def use_010(p: Project) -> Checked:
    return _dto(p, "domain")


@rule("DCA-USE-011")
def use_011(p: Project) -> Checked:
    return _dto(p, "application")


def transactional(klass: Klass) -> list[ast.AST]:
    """The code a use case runs inside its transaction boundary: what it hands to `in_transaction(...)` or
    `in_transaction_closed(...)` - a lambda, a nested function, or a method of its own."""
    out: list[ast.AST] = []
    for method in klass.methods.values():
        nested = {n.name: n for n in ast.walk(method) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for node in ast.walk(method):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("in_transaction", "in_transaction_closed")
                and node.args
            ):
                continue
            work = node.args[0]
            if isinstance(work, ast.Lambda):
                out.append(work)
            elif isinstance(work, ast.Name) and work.id in nested:
                out.append(nested[work.id])
            elif (
                isinstance(work, ast.Attribute)
                and isinstance(work.value, ast.Name)
                and work.value.id == "self"
                and work.attr in klass.methods
            ):
                out.append(klass.methods[work.attr])
    return out


@rule("DCA-USE-012")
def use_012(p: Project) -> Checked:
    """Selects the use cases. A write counts as inside the boundary in the work handed to `in_transaction`, and in a
    method of its own that only such work runs - transitively; a method an entry point also runs outside the work is
    outside."""
    found = []
    selected = use_cases(p)
    for use_case in selected:
        scopes = transactional(use_case)
        inside = {id(n) for scope in scopes for n in ast.walk(scope)}
        # The work handed over by name (`in_transaction(self._work)`) runs inside, not where it is named.
        inside |= {
            id(n.args[0])
            for n in ast.walk(use_case.node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("in_transaction", "in_transaction_closed")
            and n.args
        }
        methods = {name: method for _, name, method in p.member_methods(use_case)}
        covered: set[str] = set()
        for scope in scopes:
            covered |= _own_references(p, use_case, scope)
        outside: set[str] = set()
        todo = [n for _, n, _ in entry_points(p, use_case)]
        while todo:
            name = todo.pop()
            if name in outside or name not in methods:
                continue
            outside.add(name)
            loose = ast.Module(body=[], type_ignores=[])
            for node in ast.walk(methods[name]):
                if id(node) not in inside and isinstance(node, ast.Attribute):
                    loose.body.append(ast.Expr(node))
            todo += _own_references(p, use_case, loose)
        todo = list(covered)
        while todo:
            name = todo.pop()
            more = _own_references(p, use_case, methods[name]) - covered if name in methods else set()
            covered |= more
            todo += more
        writes = receiver_calls(
            p, use_case, {"Repository"}, lambda n: n in ("save", "delete", "delete_by_id")
        ) + receiver_calls(p, use_case, {"DomainEventPublisher"}, lambda n: n in PUBLISHES)
        for call, module, method in writes:
            if id(call) in inside or (method in covered and method not in outside):
                continue
            found.append(
                Finding(
                    module.where(call),
                    f"{use_case.name} writes outside its transaction "
                    "boundary: hand the work to TransactionBoundary.in_transaction",
                )
            )
    return Checked(len(selected), found)


def depth(klass: Klass) -> int:
    return len(klass.place.feature) - (0 if klass.module.is_package else 1)


@rule("DCA-USE-014")
def use_014(p: Project) -> Checked:
    found = []
    per_context: dict[str | None, dict[int, Klass]] = {}
    selected = [k for k in use_cases(p) if k.place.layer == "application" and not k.place.shared]
    for use_case in selected:
        per_context.setdefault(use_case.place.owner, {}).setdefault(depth(use_case), use_case)
    for owner, depths in per_context.items():
        if len(depths) > 1:
            shown = ", ".join(f"{k.module.dotted} (depth {d})" for d, k in sorted(depths.items()))
            found.append(
                Finding(min(depths.items())[1].where(), f"the use cases of {owner} sit at different depths: {shown}")
            )
    return Checked(len(selected), found)


@rule("DCA-USE-015")
def use_015(p: Project) -> Checked:
    found = []
    selected = [k for k in suffixed(p, "Result") if k.place.layer == "application"]
    for result in selected:
        todo, seen = [result], set()
        while todo:
            current = todo.pop()
            if current.qualname in seen:
                continue
            seen.add(current.qualname)
            for field in current.fields:
                for named in p.type_classes(current.module, field.annotation):
                    if p.has(named, "Entity"):
                        found.append(
                            Finding(
                                current.module.where(field.line),
                                f"{current.name}.{field.name} exposes {named.name} from {result.name}",
                            )
                        )
                    elif named.place.layer == "application":
                        todo.append(named)
    return Checked(len(selected), found)


def _depends_on(p: Project, klass: Klass) -> list[tuple[ast.AST, Module, Klass]]:
    """(node, module, class) for every project class a class depends on: in its fields, the parameters and the
    annotated locals of its methods, and every name its methods mention; its role-less bases' included."""
    out: list[tuple[ast.AST, Module, Klass]] = []
    for field in p.member_fields(klass):
        out += [
            (ast.Constant(None, lineno=field.line), field.module, k)
            for k in p.type_classes(field.module, field.annotation)
        ]
    for owner, _, method in p.member_methods(klass):
        for argument in parameters(method):
            out += [(argument, owner.module, k) for k in p.type_classes(owner.module, argument.annotation)]
        for node, name in p.refs(owner.module, ast.Module(body=method.body, type_ignores=[])):
            if name in p.classes:
                out.append((node, owner.module, p.classes[name]))
    return out


@rule("DCA-USE-016")
def use_016(p: Project) -> Checked:
    """Selects the use cases. None depends on another input port - directly, or through a class of its own module in
    the application that is no input port itself; its own interfaces and bases are no dependency."""
    found: dict[tuple[str, str], Finding] = {}
    selected = use_cases(p)
    for use_case in selected:
        own = p.ancestors(use_case) | {use_case.qualname}
        for node, module, named in _depends_on(p, use_case):
            if named.qualname in own:
                continue
            if p.has(named, "InputPort"):
                where = module.where(node)
                found.setdefault(
                    (where, named.qualname), Finding(where, f"{use_case.name} -> {named.name}: a use case drives none")
                )
            elif named.module is use_case.module and named.place.layer == "application":
                for _, _, further in _depends_on(p, named):
                    if p.has(further, "InputPort") and further.qualname not in own:
                        where = module.where(node)
                        found.setdefault(
                            (where, further.qualname),
                            Finding(
                                where, f"{use_case.name} -> {further.name} via {named.name}: a use case drives none"
                            ),
                        )
    return Checked(len(selected), list(found.values()))


@rule("DCA-USE-017")
def use_017(p: Project) -> Checked:
    selected = use_cases(p)
    return Checked(
        len(selected),
        [
            Finding(k.module.where(m), f"{k.name}.{name} is public beside execute")
            for k in selected
            for name, m in k.methods.items()
            if public(name) and name != "execute"
        ],
    )


@rule("DCA-USE-018")
def use_018(p: Project) -> Checked:
    found = []
    grouped = {k.place.owner for k in use_cases(p) if depth(k) >= 1}
    selected = p.in_layer("incoming")
    for module in selected:
        if module.place.owner not in grouped:
            continue
        features: dict[str, ast.Call] = {}
        for call, klass in p.constructions(module):
            if klass.name.endswith("Command") and klass.place.layer == "application" and klass.place.feature:
                features.setdefault(klass.place.feature[0], call)
        if len(features) > 1:
            found.append(
                Finding(
                    module.where(1),
                    f"{module.dotted} drives the commands of the features {', '.join(sorted(features))}",
                )
            )
    return Checked(len(selected), found)


def input_type(p: Project, use_case: Klass) -> list[Klass]:
    """What a use case takes: the parameters of its execute, and `I` of the `UseCase[I, O]` it names among its bases,
    transitively."""
    out: list[Klass] = []
    execute = use_case.methods.get("execute")
    if execute is not None:
        out += [n for a in parameters(execute) for n in p.type_classes(use_case.module, a.annotation)]
    for klass in [use_case, *p.lineage(use_case)]:
        for base in klass.node.bases:
            if isinstance(base, ast.Subscript) and p.resolve(klass.module, base.value) in (
                f"{BB}.UseCase",
                f"{BB}.AsyncUseCase",
            ):
                arguments = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
                out += p.type_classes(klass.module, arguments[0])
    return out


def _writes(name: str) -> bool:
    return any(name == v or name.startswith(f"{v}_") for v in WRITES)


@rule("DCA-USE-019")
def use_019(p: Project) -> Checked:
    found = []
    selected = [u for u in use_cases(p) if any(k.name.endswith("Query") for k in input_type(p, u))]
    for use_case in selected:
        for call, module, _ in receiver_calls(p, use_case, {"Repository", "Store"}, _writes) + receiver_calls(
            p, use_case, {"DomainEventPublisher", "IntegrationEventPublisher"}, lambda n: True
        ):
            found.append(Finding(module.where(call), f"the query use case {use_case.name} writes"))
    return Checked(len(selected), found)


@rule("DCA-USE-020")
def use_020(p: Project) -> Checked:
    """Selects the modules of the application."""
    found = []
    selected = p.in_layer("application")
    for module in selected:
        for node in ast.walk(module.tree):
            if isinstance(node, ast.Call) and p.resolve(module, node.func) == "uuid.UUID":
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} parses raw input into a UUID; the adapter or the id's own constructor does",
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-USE-021")
def use_021(p: Project) -> Checked:
    """Selects the use cases; a method other than `__init__` that assigns to `self` keeps state between calls."""
    selected = use_cases(p)
    return Checked(
        len(selected),
        [
            Finding(home.where(node), f"the use case {k.name} keeps state: {name} assigns to self")
            for k in selected
            for name, node, home in p.mutators(k)
        ],
    )


PRIMITIVES = {"builtins.int", "builtins.str", "builtins.bool", "builtins.float", "builtins.bytes"}


def _result_annotation(p: Project, port: Klass) -> ast.expr | None:
    """`O` of the `UseCase[I, O]` an input port names among its bases."""
    for base in port.node.bases:
        if isinstance(base, ast.Subscript) and p.resolve(port.module, base.value) == f"{BB}.UseCase":
            arguments = base.slice.elts if isinstance(base.slice, ast.Tuple) else [base.slice]
            return arguments[1] if len(arguments) > 1 else None
    return None


def _cases(node: ast.expr) -> list[ast.expr]:
    """The cases of a result annotation: the members of `A | B`, of `Optional[A]` and `Union[A, B]`, else itself.
    What a container holds (`list[str]`) is the container's business, not a case."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _cases(node.left) + _cases(node.right)
    if isinstance(node, ast.Subscript) and dotted_name(node.value) in (
        "Optional",
        "Union",
        "typing.Optional",
        "typing.Union",
    ):
        inner = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        return [case for item in inner for case in _cases(item)]
    return [node]


@rule("DCA-USE-022")
def use_022(p: Project) -> Checked:
    """Selects the input ports that name `UseCase[I, O]`; `O`, or a case of it, is no bare int, str, bool, float or
    bytes."""
    found = []
    selected = []
    for port in p.classes.values():
        result = _result_annotation(p, port) if p.has(port, "InputPort") else None
        if result is None:
            continue
        selected.append(port)
        for node in _cases(result):
            if isinstance(node, (ast.Name, ast.Attribute)) and p.resolve(port.module, node) in PRIMITIVES:
                found.append(
                    Finding(
                        port.where(),
                        f"{port.name} returns {ast.unparse(node)}; a use case's result is a type of its own, a "
                        "value or a case of a closed result",
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-USE-023")
def use_023(p: Project) -> Checked:
    """Selects every output port of the application layer, by role: a Protocol or an abstract class with the
    OutputPort role among its bases. A use case module is the deepest module or package of an application that
    declares an input port or a use case (by role or by the use-case suffix), operation containers skipped, and
    everything below it. A port declared in one is reported when a module of another names it."""
    roots: dict[str | None, set[tuple[str, ...]]] = {}
    for klass in p.classes_in("application"):
        if klass.place.shared or not klass.place.feature:
            continue
        if p.has(klass, "InputPort") or is_use_case(p, klass) or klass.name.endswith(p.layout.use_case_suffix):
            roots.setdefault(klass.place.owner, set()).add(klass.place.feature)

    def use_case_of(module: Module) -> str | None:
        place = module.place
        if place.layer != "application" or place.shared or not place.feature:
            return None
        deepest = max((r for r in roots.get(place.owner, set()) if place.feature[: len(r)] == r), key=len, default=None)
        return f"{place.owner}.{'.'.join(deepest)}" if deepest else None

    ports = [k for k in p.with_role("OutputPort") if k.place.layer == "application" and k.is_protocol]
    homes = {k.qualname: use_case_of(k.module) for k in ports}
    users: dict[str, set[str]] = {}
    for module in p.in_layer("application"):
        user = use_case_of(module)
        if user is None:
            continue
        named = {name for _, name in p.refs(module, module.tree)}
        named.update(a for item in module.imports for a in item.absolute)
        for qualname, home in homes.items():
            if home is not None and home != user and qualname in named:
                users.setdefault(qualname, set()).add(user)
    found = [
        Finding(
            p.classes[q].where(),
            f"the output port {p.classes[q].name} is declared in the use case {homes[q]} and used by "
            f"{', '.join(sorted(u))}; a port used by several use cases belongs in the shared package",
        )
        for q, u in sorted(users.items())
    ]
    return Checked(len(ports), found)
