"""Layered, onion, hexagonal and strategic rules over the imports: which layer of which context may import what."""

from __future__ import annotations

from dca_rules.model import BB, Project, dotted_name
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


TRANSACTION_DECORATORS = ("transaction.atomic", "atomic", "transactional", "Transactional")


@rule("DCA-LAY-004")
def lay_004(p: Project) -> Checked:
    found = []
    selected = p.in_layer("domain", "incoming")
    for module in selected:
        for node, name in p.refs(module, module.tree):
            if name == f"{BB}.TransactionBoundary":
                found.append(
                    Finding(
                        module.where(node),
                        f"{module.dotted} ({module.place.layer}) names "
                        "TransactionBoundary: the transaction boundary is the application's",
                    )
                )
        for item in [n for k in p.classes.values() if k.module is module for n in k.methods.values()] + [
            n for n in module.tree.body if hasattr(n, "decorator_list")
        ]:
            for decorator in getattr(item, "decorator_list", []):
                target = decorator.func if hasattr(decorator, "func") else decorator
                name = dotted_name(target) or ""
                if name in TRANSACTION_DECORATORS or name.endswith(".atomic"):
                    found.append(
                        Finding(
                            module.where(decorator),
                            f"{module.dotted} ({module.place.layer}) declares a transaction with @{name}",
                        )
                    )
    return Checked(len(selected), found)


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
            if place.layer == "infrastructure" and place.owner != module.place.owner:
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
            if module.place.sub == p.layout.event and place.layer == "api" and place.sub == "events":
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
            if place.context is not None and place.context != module.place.context and place.layer != "api":
                found.append(
                    Finding(
                        module.where(line),
                        f"{module.dotted} imports {target}: another context is reached through its api alone",
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
    if any(m.place.layer for m in p.modules.values()):
        return Checked(1, [])
    return Checked(1, [Finding(_package(p), "no module sits in a DCA layer (domain, application, adapter, ...)")])
