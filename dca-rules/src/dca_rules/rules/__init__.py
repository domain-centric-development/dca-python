"""The rules, one function per id, registered by `@rule`. Each takes the project and returns what it checked: the size
of its selection and its findings.

The selection is every element of the concept the rule governs - by role, by layer or by name: the aggregate roots
for a rule about roots, the modules of the domain for a rule about the domain's imports, the classes named `*Dto` for
a rule about DTOs. A rule whose selection is empty held over nothing; the runner reports it as `nothing selected`,
never as passed."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator

from dca_rules.model import Module, Place, Project


@dataclasses.dataclass(frozen=True, order=True)
class Finding:
    location: str
    message: str


@dataclasses.dataclass(frozen=True)
class Checked:
    """What one rule saw: how many elements its selection holds, and what it found among them."""

    selected: int
    findings: list[Finding]


Check = Callable[[Project], Checked]
RULES: dict[str, Check] = {}
#: Rules that carry doctrine only and select nothing by design: their empty selection is no gap.
DOCTRINE: set[str] = set()


def rule(rule_id: str, *, doctrine: bool = False) -> Callable[[Check], Check]:
    def register(check: Check) -> Check:
        if rule_id in RULES:
            raise ValueError(f"{rule_id} registered twice")
        RULES[rule_id] = check
        if doctrine:
            DOCTRINE.add(rule_id)
        return check

    return register


def project_imports(p: Project, module: Module) -> Iterator[tuple[int, str, Place]]:
    """(line, target module, its place) for every import of a module of the project."""
    for line, target in p.import_targets(module):
        if p.is_project(target):
            yield line, target, p.place_of(target)


def outside_imports(p: Project, module: Module) -> Iterator[tuple[int, str]]:
    """(line, target) for every import of something outside the project and the building blocks."""
    for line, target in p.import_targets(module):
        if not p.is_project(target) and not p.is_bb(target):
            yield line, target


def implemented() -> list[str]:
    return sorted(RULES)


# The modules register their rules on import.
from dca_rules.rules import (  # noqa: E402
    advanced,
    contextmap,
    cycles,
    errors,
    hexagonal,
    layers,
    naming,
    python,
    tactical,
    usecase,
)

__all__ = [
    "DOCTRINE",
    "RULES",
    "Checked",
    "Finding",
    "advanced",
    "contextmap",
    "cycles",
    "errors",
    "hexagonal",
    "implemented",
    "layers",
    "naming",
    "python",
    "rule",
    "tactical",
    "usecase",
]
