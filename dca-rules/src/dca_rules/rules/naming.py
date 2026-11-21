"""Naming rules: names that carry a role, names that hide one."""

from __future__ import annotations

import ast
import re

from dca_rules.model import Klass, Project, public
from dca_rules.rules import Checked, Finding, rule
from dca_rules.rules.hexagonal import is_use_case

BUCKETS = ("entities", "entity", "value_objects", "valueobjects", "helpers", "helper", "util", "utils")
TECHNICAL = ("Helper", "Util", "Utils", "Impl", "Implementation")
TRIGGER = re.compile(r"(?:^|(?<=[a-z0-9]))(On|After|When|Upon|Before)(?=[A-Z])")
FIELD_WRITE = re.compile(r"^(Set|Update)[A-Z]")


def input_ports(p: Project) -> list[Klass]:
    return [k for k in p.with_role("InputPort") if k.is_protocol]


@rule("DCA-NAM-001")
def nam_001(p: Project) -> Checked:
    selected = [k for k in p.classes_in("application") if is_use_case(p, k)]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the use case {k.name} does not end with {p.layout.use_case_suffix}")
            for k in selected
            if not k.name.endswith(p.layout.use_case_suffix)
        ],
    )


@rule("DCA-NAM-003")
def nam_003(p: Project) -> Checked:
    selected = [k for k in input_ports(p) if k.place.layer == "application"]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"the input port {k.name} does not end with {p.layout.input_port_suffix}")
            for k in selected
            if not k.name.endswith(p.layout.input_port_suffix)
        ],
    )


@rule("DCA-NAM-004")
def nam_004(p: Project) -> Checked:
    """Selects the interfaces of the application whose name contains the repository suffix, by name alone."""
    suffix = p.layout.repository_suffix
    selected = [k for k in p.classes_in("application") if k.is_protocol and suffix in k.name and k.name != suffix]
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} names a repository and does not end with {suffix}")
            for k in selected
            if not k.name.endswith(suffix)
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
    """Selects every module below the base package; every segment of its name counts, a namespace package's too."""
    found = []
    selected = [m for m in p.modules.values() if m.dotted != p.base]
    for module in selected:
        segments = module.dotted[len(p.base) + 1 :].split(".")
        bucket = next((s for s in segments if s in BUCKETS), None)
        if bucket is not None:
            found.append(
                Finding(
                    module.where(1), f"{module.dotted} sits in the technical bucket {bucket}; package by domain concept"
                )
            )
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
    """The input ports and use cases of the application: by role, and the classes named with the use-case suffix."""
    return [
        k for k in p.classes_in("application") if p.has(k, "InputPort") or k.name.endswith(p.layout.use_case_suffix)
    ]


def _operation(p: Project, name: str) -> str:
    """A name without the use-case or input-port suffix: what the operation is called."""
    for suffix in (p.layout.use_case_suffix, p.layout.input_port_suffix):
        if name.endswith(suffix) and name != suffix:
            return name[: -len(suffix)]
    return name


@rule("DCA-NAM-012")
def nam_012(p: Project) -> Checked:
    selected = _ports_and_use_cases(p)
    return Checked(
        len(selected),
        [
            Finding(k.where(), f"{k.name} is named after a trigger, not after its effect")
            for k in selected
            if TRIGGER.search(_operation(p, k.name))
        ],
    )


@rule("DCA-NAM-013")
def nam_013(p: Project) -> Checked:
    """Selects the input ports and use cases, and the modules of the api packages - their public functions and the
    public methods of their classes; the events package is no api."""
    ports = _ports_and_use_cases(p)
    published = [m for m in p.in_layer("api") if m.place.sub != "events"]
    found = [
        Finding(k.where(), f"{k.name} is named after a field it writes")
        for k in ports
        if FIELD_WRITE.match(_operation(p, k.name))
    ]
    for module in published:
        operations: list[tuple[str, ast.AST]] = [
            (node.name, node) for node in module.tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        operations += [
            (f"{k.name}.{name}", method)
            for k in p.classes.values()
            if k.module is module
            for name, method in k.methods.items()
        ]
        for name, node in operations:
            last = name.rsplit(".", 1)[-1]
            if public(last) and last.startswith(("set_", "update_")):
                found.append(
                    Finding(module.where(node), f"the published operation {name} is named after a field it writes")
                )
    return Checked(len(ports) + len(published), found)
