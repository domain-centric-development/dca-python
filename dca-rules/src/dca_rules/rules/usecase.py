"""Use-case rules: commands, queries, results, the use case's shape and what it may call."""

from __future__ import annotations

import ast

from dca_rules.model import Klass, Project, parameters, public
from dca_rules.rules import Checked, Finding, rule
from dca_rules.rules.hexagonal import is_use_case

WRITES = ("save", "delete", "delete_by_id", "remove", "add", "insert", "update", "append", "put", "store")
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


def _placed(p: Project, suffix: str, layers: tuple[str, ...], where: str) -> Checked:
    selected = [k for k in suffixed(p, suffix) if not p.has(k, "Value")]
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
            Finding(klass.module.where(f.line), f"{klass.name}.{f.name} is a mutable collection")
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
    return _placed(p, "Result", ("application",), "the application")


@rule("DCA-USE-007")
def use_007(p: Project) -> Checked:
    return _immutable(p, "Result")


@rule("DCA-USE-008")
def use_008(p: Project) -> Checked:
    return _placed(p, "Response", ("incoming", "outgoing", "adapter"), "the adapters")


def receiver_calls(p: Project, klass: Klass, roles: set[str], names: tuple[str, ...]) -> list[ast.Call]:
    return [
        call
        for method in klass.methods.values()
        for call, name, held in p.calls(klass, method)
        if name in names and held & roles
    ]


@rule("DCA-USE-009")
def use_009(p: Project) -> Checked:
    found = []
    selected = use_cases(p)
    for use_case in selected:
        saves = receiver_calls(p, use_case, {"Repository"}, ("save",))
        if saves and not receiver_calls(p, use_case, {"DomainEventPublisher"}, PUBLISHES):
            found.append(
                Finding(
                    use_case.module.where(saves[0]),
                    f"{use_case.name} saves an aggregate and publishes none of its events",
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
    found = []
    selected = use_cases(p)
    for use_case in selected:
        inside = {id(n) for scope in transactional(use_case) for n in ast.walk(scope)}
        writes = receiver_calls(p, use_case, {"Repository"}, ("save", "delete", "delete_by_id")) + receiver_calls(
            p, use_case, {"DomainEventPublisher"}, PUBLISHES
        )
        for call in writes:
            if id(call) not in inside:
                found.append(
                    Finding(
                        use_case.module.where(call),
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


@rule("DCA-USE-016")
def use_016(p: Project) -> Checked:
    found = []
    selected = use_cases(p)
    for use_case in selected:
        for field in use_case.fields:
            for named in p.type_classes(use_case.module, field.annotation):
                if p.has(named, "InputPort"):
                    found.append(
                        Finding(
                            use_case.module.where(field.line),
                            f"{use_case.name}.{field.name} holds the use case {named.name}",
                        )
                    )
    return Checked(len(selected), found)


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
    execute = use_case.methods.get("execute")
    if execute is None:
        return []
    return [n for a in parameters(execute) for n in p.type_classes(use_case.module, a.annotation)]


@rule("DCA-USE-019")
def use_019(p: Project) -> Checked:
    found = []
    selected = [u for u in use_cases(p) if any(k.name.endswith("Query") for k in input_type(p, u))]
    for use_case in selected:
        for call in receiver_calls(p, use_case, {"Repository", "Store"}, WRITES) + receiver_calls(
            p, use_case, {"DomainEventPublisher", "IntegrationEventPublisher"}, PUBLISHES
        ):
            found.append(Finding(use_case.module.where(call), f"the query use case {use_case.name} writes"))
    return Checked(len(selected), found)


@rule("DCA-USE-020")
def use_020(p: Project) -> Checked:
    found = []
    selected = use_cases(p)
    for use_case in selected:
        for node in ast.walk(use_case.node):
            if isinstance(node, ast.Call) and p.resolve(use_case.module, node.func) == "uuid.UUID":
                found.append(
                    Finding(
                        use_case.module.where(node),
                        f"{use_case.name} parses raw input into a UUID; the adapter or the id's own constructor does",
                    )
                )
    return Checked(len(selected), found)
