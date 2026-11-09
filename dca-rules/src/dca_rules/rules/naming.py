"""Naming rules: names that carry a role, names that hide one."""

from __future__ import annotations

import ast
import re

from dca_rules.model import Klass, Project, public
from dca_rules.rules import Checked, Finding, rule
from dca_rules.rules.hexagonal import is_use_case

BUCKETS = ("entities", "entity", "value_objects", "valueobjects", "helpers", "helper", "util", "utils")
TECHNICAL = ("Helper", "Util", "Utils", "Impl", "Implementation")
TRIGGER = re.compile(r"^(On|After|When|Upon|Before)[A-Z]")
FIELD_WRITE = re.compile(r"^(Set|Update)[A-Z]")


def input_ports(p: Project) -> list[Klass]:
    return [k for k in p.with_role("InputPort") if k.is_protocol]


@rule("DCA-NAM-001")
def nam_001(p: Project) -> Checked:
    selected = [k for k in p.classes_in("application") if is_use_case(p, k)]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the use case {k.name} does not end with UseCase")
            for k in selected
            if not k.name.endswith("UseCase")
        ],
    )


@rule("DCA-NAM-003")
def nam_003(p: Project) -> Checked:
    selected = [k for k in input_ports(p) if k.place.layer == "application"]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the input port {k.name} does not end with InputPort")
            for k in selected
            if not k.name.endswith("InputPort")
        ],
    )


@rule("DCA-NAM-004")
def nam_004(p: Project) -> Checked:
    selected = [k for k in p.classes_in("application") if "Repository" in k.name or p.has(k, "Repository")]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} names a repository and does not end with Repository")
            for k in selected
            if "Repository" in k.name and not k.name.endswith("Repository")
        ],
    )


def _suffix_in(p: Project, suffix: str, layers: tuple[str, ...], where: str) -> Checked:
    selected = [k for k in p.classes.values() if k.name.lower().endswith(suffix.lower())]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} sits in {k.module.dotted}, outside {where}")
            for k in selected
            if k.place.layer not in layers
        ],
    )


@rule("DCA-NAM-007")
def nam_007(p: Project) -> Checked:
    return _suffix_in(p, "Dto", ("incoming", "outgoing", "adapter"), "the adapters")


@rule("DCA-NAM-008")
def nam_008(p: Project) -> Checked:
    return _suffix_in(p, "Converter", ("incoming", "outgoing", "adapter"), "the adapters")


@rule("DCA-NAM-009")
def nam_009(p: Project) -> Checked:
    found = []
    selected = [m for m in p.modules.values() if m.place.context or m.place.kernel]
    for module in selected:
        last = module.dotted.rsplit(".", 1)[-1]
        if last in BUCKETS:
            found.append(Finding(module.where(1), f"{module.dotted} is a technical bucket; package by domain concept"))
    return Checked(len(selected), found)


@rule("DCA-NAM-010")
def nam_010(p: Project) -> Checked:
    selected = p.classes_in("domain")
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the domain class {k.name} carries a technical suffix")
            for k in selected
            if k.name.endswith(TECHNICAL)
        ],
    )


@rule("DCA-NAM-011")
def nam_011(p: Project) -> Checked:
    selected = [k for k in p.classes.values() if k.name.endswith("ViewModel")]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} sits in {k.module.dotted}, outside the incoming web adapter")
            for k in selected
            if not (k.place.layer == "incoming" and k.place.sub == p.layout.web)
        ],
    )


def _ports_and_use_cases(p: Project) -> list[Klass]:
    return [k for k in p.classes_in("application") if p.has(k, "InputPort")]


@rule("DCA-NAM-012")
def nam_012(p: Project) -> Checked:
    selected = _ports_and_use_cases(p)
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} is named after a trigger, not after its effect")
            for k in selected
            if TRIGGER.match(k.name)
        ],
    )


@rule("DCA-NAM-013")
def nam_013(p: Project) -> Checked:
    """Selects the input ports and use cases, and the modules of the api packages."""
    ports = _ports_and_use_cases(p)
    published = p.in_layer("api")
    found = [
        Finding(k.where(), f"{k.name} is named after a field it writes") for k in ports if FIELD_WRITE.match(k.name)
    ]
    for module in published:
        for node in module.tree.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and public(node.name)
                and node.name.startswith(("set_", "update_"))
            ):
                found.append(
                    Finding(module.where(node), f"the published operation {node.name} is named after a field it writes")
                )
    return Checked(len(ports) + len(published), found)
