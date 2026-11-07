"""The Domain-Centric Architecture rule suite for Python.

The rules carry the same ids as the Java, .NET and Rust suites. They read the project's source with `ast` and
import nothing of it. A project declares its layout in `[tool.dca]` of its `pyproject.toml` and runs every
implemented rule as its own test:

    # tests/architecture/test_architecture.py
    from dca_rules.testing import architecture_tests

    test_dca = architecture_tests("pyproject.toml")   # one test per id: test_dca[DCA-TAC-003], ...

A violation fails its test with one line per finding, the rule id first.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib.resources
import json
import typing

from dca_rules.layout import DcaLayout
from dca_rules.model import Project
from dca_rules.rules import RULES, Finding, implemented


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
    """What running one rule produced: `ran` with findings (an informational rule never fails), or why it did not
    run - `experimental` (not switched on) or `disabled`."""

    kind: typing.Literal["ran", "experimental", "disabled"]
    findings: tuple[Finding, ...] = ()
    informational: bool = False


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
    findings = tuple(sorted(set(RULES[rule_id](project))))
    return Outcome("ran", findings, entry.status == "informational")


def report(rule_id: str, outcome: Outcome) -> str:
    title = catalogue()[rule_id].title
    if outcome.kind != "ran":
        return f"[{rule_id}] {outcome.kind}, not run"
    lines = [f"[{rule_id}] {f.location}: {f.message}" for f in outcome.findings]
    head = f"[{rule_id}] {title}"
    if outcome.informational:
        head += f": {len(outcome.findings)} listed (informational, never fails)"
    return "\n".join([head, *lines])


__all__ = ["DcaLayout", "Entry", "Finding", "Outcome", "Project", "catalogue", "implemented", "report", "run"]
