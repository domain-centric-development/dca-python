"""Layered, onion, hexagonal and strategic rules over the imports: which layer of which context may import what."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from dca_rules.model import BB, Module, Project
from dca_rules.rules import Checked, Finding, outside_imports, project_imports, rule

INFRA = ("infrastructure", "root")
ADAPTERS = ("incoming", "outgoing", "adapter")


def _imports_into(p: Project, layers: tuple[str, ...], targets: tuple[str, ...], what: str) -> Checked:
    found = []
    selected = p.in_layer(*layers)
    for module in selected:
        for line, target, place in project_imports(p, module):
            if place.layer in targets:
                found.append(
                    Finding(
                        module.where(line),
                        f"{module.dotted} ({module.place.layer}) imports {target} ({place.layer}): {what}",
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-LAY-001", doctrine=True)
def lay_001(p: Project) -> Checked:
    return Checked(0, [])


@rule("DCA-LAY-002")
def lay_002(p: Project) -> Checked:
    return _imports_into(p, ("domain",), INFRA, "the domain depends on no infrastructure")


@rule("DCA-LAY-003")
def lay_003(p: Project) -> Checked:
    checked = _imports_into(p, ("application",), INFRA, "the application reaches infrastructure through its ports")
    found = list(checked.findings)
    for module in p.in_layer("application"):
        for line, target in outside_imports(p, module):
            if p.is_framework(target):
                found.append(
                    Finding(
                        module.where(line),
                        f"{module.dotted} imports the framework module {target}: "
                        "the application reaches it through an output port",
                    )
                )
    return Checked(checked.selected, found)


def _matches(name: str, entries: tuple[str, ...]) -> bool:
    return any(name == e or name.endswith("." + e) for e in entries if not e.startswith("."))


#: The transaction boundary, synchronous and asynchronous: naming one is wiring (DCA-LAY-004).
BOUNDARIES = {f"{BB}.TransactionBoundary", f"{BB}.AsyncTransactionBoundary"}


def _transactions(p: Project, module: Module) -> Iterator[tuple[ast.AST, str, bool]]:
    """(node, what, wiring) for every place a module touches a transaction: a transactional decorator, a transaction
    API called or entered, and - wiring - a name of TransactionBoundary other than the base of an implementation."""
    layout = p.layout
    bases: set[int] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                target = base.value if isinstance(base, ast.Subscript) else base
                if p.resolve(module, target) in BOUNDARIES:
                    bases.update(id(n) for n in ast.walk(base))
    for node, name in p.refs(module, module.tree):
        if name in BOUNDARIES and id(node) not in bases:
            yield node, "names TransactionBoundary", True
    methods = {e[1:] for e in layout.transaction_apis if e.startswith(".")}
    decorators = {id(d) for n in ast.walk(module.tree) for d in getattr(n, "decorator_list", [])}
    for node in ast.walk(module.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                name = p.resolve(module, decorator.func if isinstance(decorator, ast.Call) else decorator) or ""
                if _matches(name, layout.transaction_decorators):
                    yield decorator, f"declares a transaction with @{name}", False
        elif isinstance(node, ast.Call) and id(node) not in decorators:
            name = p.resolve(module, node.func) or ""
            if name and _matches(name, layout.transaction_apis):
                yield node, f"runs a transaction with {name}", False
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr in methods
                    and not _matches(p.resolve(module, call.func) or "", layout.transaction_apis)
                ):
                    yield call, f"runs a transaction with .{call.func.attr}()", False


@rule("DCA-LAY-004")
def lay_004(p: Project) -> Checked:
    """Selects every module in a layer. A transactional decorator and a transaction run in code belong to the
    application and the outgoing adapters; naming TransactionBoundary (wiring) to those and to the composition root
    and the shared kernel's infrastructure. An implementation of TransactionBoundary is no use of it."""
    found = []
    selected = [m for m in p.modules.values() if m.place.layer]
    for module in selected:
        place = module.place
        for node, what, wiring in _transactions(p, module):
            allowed = place.layer in ("application", "outgoing") or (
                wiring and (place.layer == "root" or (place.kernel and place.layer == "infrastructure"))
            )
            if not allowed:
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} ({place.layer}) {what}: the transaction boundary is the application's",
                    )
                )
    return Checked(len(selected), sorted(set(found)))


@rule("DCA-LAY-007")
def lay_007(p: Project) -> Checked:
    found = []
    for module in p.modules.values():
        place = module.place
        if place.layer is not None or module.dotted == p.base:
            continue
        if (place.context or place.kernel) and module.is_package and module.dotted.count(".") == p.base.count(".") + 1:
            continue
        if any(True for _ in p.classes.values() if _.module is module) or module.tree.body:
            found.append(Finding(module.where(1), f"{module.dotted} sits in no layer"))
    return Checked(len(p.modules), found)


@rule("DCA-ONI-001")
def oni_001(p: Project) -> Checked:
    return _imports_into(p, ("domain",), ("application",), "the domain is the innermost layer")


@rule("DCA-ONI-002")
def oni_002(p: Project) -> Checked:
    found = []
    allowed = p.layout.allowed_in_domain
    selected = p.in_layer("domain")
    for module in selected:
        for line, target in outside_imports(p, module):
            if p.is_stdlib(target) or any(target == a or target.startswith(a + ".") for a in allowed):
                continue
            found.append(
                Finding(
                    module.where(line),
                    f"{module.dotted} imports {target}: the domain uses the "
                    "standard library, the building blocks and the allowed libraries only",
                )
            )
    return Checked(len(selected), found)


@rule("DCA-HEX-001")
def hex_001(p: Project) -> Checked:
    return _imports_into(p, ("domain",), ADAPTERS, "the domain knows no adapter")


@rule("DCA-HEX-002")
def hex_002(p: Project) -> Checked:
    return _imports_into(p, ("application",), ADAPTERS, "the application knows no adapter")


@rule("DCA-HEX-004")
def hex_004(p: Project) -> Checked:
    return _imports_into(p, ("incoming",), INFRA, "an incoming adapter uses input ports, not infrastructure")


@rule("DCA-HEX-005")
def hex_005(p: Project) -> Checked:
    found = []
    selected = p.in_layer("outgoing")
    for module in selected:
        for line, target, place in project_imports(p, module):
            # Its own context's infrastructure and the shared kernel's are shared support; another context's is not.
            if place.layer == "infrastructure" and place.owner != module.place.owner and not place.kernel:
                found.append(
                    Finding(
                        module.where(line), f"{module.dotted} imports {target}, the infrastructure of {place.owner}"
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-HEX-006")
def hex_006(p: Project) -> Checked:
    found = []
    selected = [m for m in p.in_layer("incoming") if m.place.sub != p.layout.event]
    for module in selected:
        for line, target, place in project_imports(p, module):
            if place.layer == "outgoing" and place.owner == module.place.owner:
                found.append(Finding(module.where(line), f"{module.dotted} imports the outgoing adapter {target}"))
    return Checked(len(selected), found)


@rule("DCA-HEX-007")
def hex_007(p: Project) -> Checked:
    found = []
    selected = p.in_layer("incoming")
    for module in selected:
        for line, target, place in project_imports(p, module):
            if place.context is None or place.context == module.place.context:
                continue
            if module.place.sub == p.layout.event and place.layer == "events":
                continue
            found.append(
                Finding(module.where(line), f"{module.dotted} imports {target} of the context {place.context}")
            )
    return Checked(len(selected), found)


@rule("DCA-STR-001")
def str_001(p: Project) -> Checked:
    declared = p.declared_contexts()
    found = []
    for package in sorted(p.contexts):
        name = declared.get(package, f"{package} (undeclared)")
        modules = sum(1 for m in p.modules.values() if m.place.context == package)
        found.append(Finding(f"{p.base}.{package}", f"bounded context {name}: {modules} modules"))
    if any(m.place.kernel for m in p.modules.values()):
        found.append(Finding(f"{p.base}.{p.layout.shared_kernel}", "shared kernel"))
    return Checked(len(found), found)


@rule("DCA-STR-002")
def str_002(p: Project) -> Checked:
    found = []
    selected = [m for m in p.modules.values() if m.place.kernel]
    for module in selected:
        for line, target, place in project_imports(p, module):
            if place.context is not None:
                found.append(
                    Finding(module.where(line), f"the shared kernel imports {target} of the context {place.context}")
                )
    return Checked(len(selected), found)


def _other_context(p: Project, layer: str, what: str) -> Checked:
    found = []
    selected = [m for m in p.in_layer(layer) if m.place.context is not None]
    for module in selected:
        for line, target, place in project_imports(p, module):
            if place.context is not None and place.context != module.place.context:
                found.append(
                    Finding(
                        module.where(line),
                        f"the {layer} of {module.place.context} imports {target} of {place.context}: {what}",
                    )
                )
    return Checked(len(selected), found)


@rule("DCA-STR-003")
def str_003(p: Project) -> Checked:
    return _other_context(p, "application", "an application reaches another context through an output port")


@rule("DCA-STR-004")
def str_004(p: Project) -> Checked:
    return _other_context(p, "domain", "a domain knows no other context")


@rule("DCA-STR-006")
def str_006(p: Project) -> Checked:
    found = []
    selected = [m for m in p.in_layer(*ADAPTERS) if m.place.context is not None]
    for module in selected:
        for line, target, place in project_imports(p, module):
            if (
                place.context is not None
                and place.context != module.place.context
                and place.layer not in ("api", "events")
            ):
                found.append(
                    Finding(
                        module.where(line),
                        f"{module.dotted} imports {target}: another context is reached through its api and events",
                    )
                )
    return Checked(len(selected), found)


def _package(p: Project) -> str:
    return str(p.layout.package_dir.relative_to(p.layout.project_root))


@rule("DCA-STR-011")
def str_011(p: Project) -> Checked:
    """Selects the project's package as a whole."""
    if p.declared_contexts():
        return Checked(1, [])
    return Checked(
        1,
        [
            Finding(
                _package(p), "no package declares a bounded context: __dca__ = BoundedContext(...) in its __init__.py"
            )
        ],
    )


@rule("DCA-STR-012")
def str_012(p: Project) -> Checked:
    """Selects the project's package as a whole."""
    if any(m.place.layer and m.place.layer != "root" for m in p.modules.values()):
        return Checked(1, [])
    return Checked(1, [Finding(_package(p), "no module sits in a DCA layer (domain, application, adapter, ...)")])
