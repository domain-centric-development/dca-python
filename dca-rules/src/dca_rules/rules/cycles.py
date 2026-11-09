"""Cycle rules: slices of the code that must not import each other in a circle."""

from __future__ import annotations

from collections.abc import Callable

from dca_rules.model import Module, Place, Project
from dca_rules.rules import Checked, Finding, project_imports, rule

Slice = Callable[[Place], str | None]


def cycles(p: Project, slice_of: Slice, what: str) -> Checked:
    """Every cycle between slices, each once; the finding names the import that closes it. Selects the modules that
    fall into a slice."""
    edges: dict[str, dict[str, tuple[Module, int]]] = {}
    selected = 0
    for module in p.modules.values():
        source = slice_of(module.place)
        if source is None:
            continue
        selected += 1
        for line, _target, place in project_imports(p, module):
            target = slice_of(place)
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
    def slice_of(place: Place) -> str | None:
        if place.layer != "application" or place.shared or not place.feature:
            return None
        return f"{place.owner}.{place.feature[0]}"

    return cycles(p, slice_of, "feature")
