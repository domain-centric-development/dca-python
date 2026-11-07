"""The rules, one function per id, registered by `@rule`. Each takes the project and returns its findings."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterator

from dca_rules.model import Module, Place, Project


@dataclasses.dataclass(frozen=True, order=True)
class Finding:
    location: str
    message: str


Check = Callable[[Project], list[Finding]]
RULES: dict[str, Check] = {}


def rule(rule_id: str) -> Callable[[Check], Check]:
    def register(check: Check) -> Check:
        if rule_id in RULES:
            raise ValueError(f"{rule_id} registered twice")
        RULES[rule_id] = check
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
    "RULES",
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
