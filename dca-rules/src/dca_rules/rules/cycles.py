"""Cycle rules: slices of the code that must not import each other in a circle."""

from __future__ import annotations

from collections.abc import Callable

from dca_rules.model import Module, Place, Project
from dca_rules.rules import Checked, Finding, project_imports, rule
from dca_rules.rules.hexagonal import is_use_case

Slice = Callable[[Place], str | None]


def cycles(
    p: Project,
    slice_of: Slice,
    what: str,
    skip: Callable[[Module, str], bool] | None = None,
) -> Checked:
    """Every cycle between slices, each once; the finding names the import that closes it. Selects the modules that
    fall into a slice. `skip` leaves out an import that is no dependency between slices."""

    edges: dict[str, dict[str, tuple[Module, int]]] = {}
    selected = 0
    for module in p.modules.values():
        source = slice_of(module.place)
        if source is None:
            continue
        selected += 1
        for line, target_name, target_place in project_imports(p, module):
            if skip is not None and skip(module, target_name):
                continue
            target = slice_of(target_place)
            if target is not None and target != source:
                edges.setdefault(source, {}).setdefault(target, (module, line))
    found, seen = [], set()
    for start in sorted(edges):
        stack = [(start, [start])]
        while stack:
            node, path = stack.pop()
            for nxt in sorted(edges.get(node, {})):
                if nxt == start:
                    key = frozenset(path)
                    if key not in seen:
                        seen.add(key)
                        module, line = edges[node][nxt]
                        found.append(Finding(module.where(line), f"{what} cycle: {' -> '.join([*path, start])}"))
                elif nxt not in path and nxt > start:
                    stack.append((nxt, [*path, nxt]))
    return Checked(selected, found)


def _per_context(layer: str) -> Slice:
    return lambda place: place.owner if place.layer == layer else None


@rule("DCA-CYC-001")
def cyc_001(p: Project) -> Checked:
    return cycles(p, _per_context("domain"), "domain")


@rule("DCA-CYC-002")
def cyc_002(p: Project) -> Checked:
    return cycles(p, _per_context("application"), "application")


@rule("DCA-CYC-003")
def cyc_003(p: Project) -> Checked:
    return cycles(p, _per_context("outgoing"), "outgoing adapter")


@rule("DCA-CYC-004")
def cyc_004(p: Project) -> Checked:
    return cycles(p, _per_context("incoming"), "incoming adapter")


@rule("DCA-CYC-005")
def cyc_005(p: Project) -> Checked:
    """One slice per operation root: the deepest module or package of an application, operation containers skipped,
    that declares an input port or a use case (by role or by the use-case suffix); a module below it joins it. A
    module on the way to an operation root that is none itself is the feature slice of its first segment. A package's
    `__init__` that imports a module below itself re-exports it: no dependency."""
    roots: dict[str | None, set[tuple[str, ...]]] = {}
    for klass in p.classes_in("application"):
        if klass.place.shared or not klass.place.feature:
            continue
        if p.has(klass, "InputPort") or is_use_case(p, klass) or klass.name.endswith(p.layout.use_case_suffix):
            roots.setdefault(klass.place.owner, set()).add(klass.place.feature)

    def slice_of(place: Place) -> str | None:
        if place.layer != "application" or place.shared or not place.feature:
            return None
        ops = roots.get(place.owner, set())
        feature = place.feature
        deepest = max((r for r in ops if feature[: len(r)] == r), key=len, default=None)
        if deepest is None and any(len(r) > 1 and r[0] == feature[0] for r in ops):
            deepest = feature[:1]
        return f"{place.owner}.{'.'.join(deepest)}" if deepest else None

    def reexport(module: Module, target: str) -> bool:
        return module.is_package and target.startswith(module.dotted + ".")

    return cycles(p, slice_of, "feature", skip=reexport)
