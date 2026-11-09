"""The Domain-Centric Architecture rule suite for Python.

The rules carry the same ids as the Java, .NET and Rust suites. They read the project's source with `ast` and
import nothing of it. A project declares its layout in `[tool.dca]` of its `pyproject.toml` and runs every
implemented rule as its own test:

    # tests/architecture/test_architecture.py
    from dca_rules.testing import architecture_tests

    test_dca = architecture_tests("pyproject.toml")   # one test per id: test_dca[DCA-TAC-003], ...

A violation fails its test with one line per finding, the rule id first. A rule whose selection is empty - no
element of the concept it governs, say no class carries the role it selects by - fails too, as `nothing selected`:
green would say it held. A project that has none of a concept on purpose says so once, with the reason:

    [tool.dca]
    allow-empty = [{ rule = "DCA-ADV-013", reason = "the model builds every aggregate through its own class" }]
"""

from __future__ import annotations

import dataclasses
import functools
import importlib.resources
import json
import typing

from dca_rules.layout import DcaLayout
from dca_rules.model import Project
from dca_rules.rules import DOCTRINE, RULES, Checked, Finding, implemented


@dataclasses.dataclass(frozen=True)
class Entry:
    id: str
    title: str
    status: str
    maturity: str


@functools.cache
def catalogue() -> dict[str, Entry]:
    """Every DCA id with its Python meaning, from the packaged `rules.json`."""
    text = importlib.resources.files("dca_rules").joinpath("rules.json").read_text(encoding="utf-8")
    out = {}
    for item in json.loads(text)["rules"]:
        out[item["id"]] = Entry(
            item["id"], item.get("title", ""), item.get("status", "enforced"), item.get("maturity", "released")
        )
    return out


@dataclasses.dataclass(frozen=True)
class Outcome:
    """What running one rule produced: `ran` with findings over a selection of `selected` elements (an informational
    rule never fails); `empty` when the selection held nothing, so the rule held over nothing - `allowed` carries the
    project's reason when `[tool.dca] allow-empty` names the rule; or why it did not run - `experimental` (not
    switched on) or `disabled`."""

    kind: typing.Literal["ran", "empty", "experimental", "disabled"]
    findings: tuple[Finding, ...] = ()
    informational: bool = False
    selected: int = 0
    allowed: str | None = None

    @property
    def fails(self) -> bool:
        """Whether this outcome fails the build: a finding of an enforced rule, or an empty selection the project
        does not allow."""
        if self.informational:
            return False
        if self.kind == "empty":
            return self.allowed is None
        return self.kind == "ran" and bool(self.findings)


def run(project: Project, rule_id: str) -> Outcome:
    if rule_id not in RULES:
        raise KeyError(f"{rule_id} is not implemented by dca-rules")
    entry = catalogue().get(rule_id)
    if entry is None:
        raise KeyError(f"{rule_id} is not in rules.json")
    if rule_id in project.layout.disabled:
        return Outcome("disabled")
    if entry.maturity == "experimental" and not project.layout.experimental_on(rule_id):
        return Outcome("experimental")
    checked: Checked = RULES[rule_id](project)
    findings = tuple(sorted(set(checked.findings)))
    informational = entry.status == "informational"
    allowed = project.layout.allowed_empty(rule_id)
    if checked.selected == 0 and not findings and rule_id not in DOCTRINE:
        return Outcome("empty", (), informational, 0, allowed)
    return Outcome("ran", findings, informational, checked.selected, allowed)


def report(rule_id: str, outcome: Outcome) -> str:
    title = catalogue()[rule_id].title
    if outcome.kind == "empty":
        if outcome.allowed is not None:
            return f"[{rule_id}] {title}: nothing selected, allowed: {outcome.allowed}"
        return (
            f"[{rule_id}] {title}: nothing selected - the rule held over nothing. When the project has none of what it "
            f"governs on purpose, name it in [tool.dca] allow-empty with the reason"
        )
    if outcome.kind != "ran":
        return f"[{rule_id}] {outcome.kind}, not run"
    lines = [f"[{rule_id}] {f.location}: {f.message}" for f in outcome.findings]
    head = f"[{rule_id}] {title} ({outcome.selected} selected)"
    if outcome.informational:
        head += f": {len(outcome.findings)} listed (informational, never fails)"
    if outcome.allowed is not None and outcome.selected:
        head += f"; allow-empty names it, take it out: it selects {outcome.selected} now"
    return "\n".join([head, *lines])


__all__ = [
    "Checked",
    "DcaLayout",
    "Entry",
    "Finding",
    "Outcome",
    "Project",
    "catalogue",
    "implemented",
    "report",
    "run",
]
